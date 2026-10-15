import concurrent.futures
import tempfile
import unittest
from pathlib import Path
from reserve_cart import store,create_app,create_admin


class OrderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=str(Path(self.temp.name)/'test.sqlite3');store.initialize(self.path)
        self.product=store.save_product(self.path,dict(sku='A',name='Cup',description='A cup',category='Table',price_cents=2800,stock=2,art='cup'))['id']
    def payload(self,**changes):return {**dict(idempotency_key='checkout-key-001',name='Ada',email='ada@example.org',note='',items=[{'product_id':self.product,'quantity':1}]),**changes}
    def reserve(self,**changes):return store.reserve(self.path,'owner',self.payload(**changes),now=1000,ttl=60)
    def action(self,order,action,key='action-request-001',now=1010):return store.transition(self.path,{'action':action,'idempotency_key':key,'note':'External confirmation'},'admin',order_id=order['id'],now=now)
    def stock(self,now=1000):return store.catalog(self.path,now)[0]['stock']
    def test_checkout_reserves_stock(self):
        order=self.reserve();self.assertEqual(order['total_cents'],2800);self.assertEqual(self.stock(),1)
    def test_expiration_restores_exactly_once(self):
        self.reserve();self.assertEqual(store.sweep(self.path,1060),1);self.assertEqual(store.sweep(self.path,1061),0);self.assertEqual(self.stock(1061),2)
    def test_retry_returns_same_private_link(self):
        a=self.reserve();b=self.reserve();self.assertEqual(a,b);self.assertEqual(self.stock(),1)
    def test_same_key_other_body_rejected(self):
        self.reserve()
        with self.assertRaises(store.Error):self.reserve(name='Other')
    def test_keys_are_scoped_to_session_owner(self):
        a=self.reserve();b=store.reserve(self.path,'different-owner',self.payload(),now=1000,ttl=60)
        self.assertNotEqual(a['token'],b['token'])
    def test_last_unit_race(self):
        store.adjust_stock(self.path,self.product,{'delta':-1,'reason':'Fixture'})
        def attempt(owner):
            try:return store.reserve(self.path,owner,self.payload(),now=1000,ttl=60)
            except store.Error:return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,['a','b']))
        self.assertEqual(sum(r is not None for r in results),1);self.assertEqual(self.stock(),0)
    def test_failed_multiline_cart_is_atomic(self):
        with self.assertRaises(store.Error):self.reserve(items=[{'product_id':self.product,'quantity':1},{'product_id':999,'quantity':1}])
        self.assertEqual(self.stock(),2)
    def test_expired_order_cannot_be_paid(self):
        order=self.reserve()
        with self.assertRaises(store.Error):self.action(order,'pay',now=1060)
        self.assertEqual(self.stock(1060),2);self.assertEqual(store.get_order(self.path,order['token'],1060)['status'],'expired')
    def test_paid_order_does_not_expire(self):
        order=self.reserve();self.action(order,'pay');self.assertEqual(store.sweep(self.path,9999),0);self.assertEqual(self.stock(9999),1)
    def test_payment_ready_collection_sequence(self):
        order=self.reserve();self.action(order,'pay');self.action(order,'ready','action-ready-001');result=self.action(order,'collect','action-collect-001')
        self.assertEqual(result['status'],'collected');self.assertEqual(self.stock(),1)
    def test_cannot_skip_payment(self):
        with self.assertRaises(store.Error):self.action(self.reserve(),'ready')
    def test_customer_cannot_mark_paid(self):
        order=self.reserve()
        with self.assertRaises(store.Error):store.transition(self.path,{'action':'pay','idempotency_key':'customer-pay-001','note':'x'},'customer',token=order['token'],now=1010)
    def test_cancellation_retry_does_not_duplicate_stock(self):
        order=self.reserve();payload={'action':'cancel','idempotency_key':'cancel-request-001','note':''}
        for _ in range(2):store.transition(self.path,payload,'customer',token=order['token'],now=1010)
        self.assertEqual(self.stock(),2)
    def test_refund_restores_and_requires_reference(self):
        order=self.reserve();self.action(order,'pay')
        with self.assertRaises(store.Error):store.transition(self.path,{'action':'refund','idempotency_key':'refund-bad-001'},'admin',order_id=order['id'],now=1010)
        result=self.action(order,'refund','refund-good-001');self.assertEqual(result['status'],'refunded');self.assertEqual(self.stock(),2)
    def test_private_view_omits_contact_data_and_token(self):
        order=self.reserve();public=store.get_order(self.path,order['token'],1010)
        for key in ['email','customer_name','note','token','owner']:self.assertNotIn(key,public)
    def test_wrong_capability_denied(self):
        self.reserve()
        with self.assertRaises(store.Error):store.get_order(self.path,'incorrect-token',1010)
    def test_price_changes_do_not_reprice_order(self):
        order=self.reserve();store.save_product(self.path,dict(name='New cup',description='New',category='Table',price_cents=9900,art='cup',active=1),self.product)
        self.assertEqual(store.get_order(self.path,order['token'],1010)['total_cents'],2800)
    def test_boolean_quantity_rejected(self):
        with self.assertRaises(store.Error):self.reserve(items=[{'product_id':self.product,'quantity':True}])
    def test_stock_ledger_balances(self):
        order=self.reserve();self.action(order,'cancel')
        db=store.connect(self.path)
        try:self.assertEqual(db.execute('SELECT sum(delta) FROM stock_ledger').fetchone()[0],2)
        finally:db.close()
    def test_archived_product_not_reservable(self):
        store.save_product(self.path,dict(name='Cup',description='x',category='Table',price_cents=1,art='cup',active=0),self.product)
        with self.assertRaises(store.Error):self.reserve()


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=str(Path(self.temp.name)/'web.sqlite3');self.app=create_app({'TESTING':True,'DATABASE':self.path,'SECRET_KEY':'test-only-secret','CLOCK':lambda:1000})
        create_admin(self.path,'browser-test-password');self.client=self.app.test_client();self.csrf=self.client.get('/api/session').json['csrf']
    def post(self,path,payload,token=None):return self.client.post(path,json=payload,headers={'X-CSRF-Token':self.csrf,**({'Authorization':'Bearer '+token} if token else {})})
    def test_public_products_and_private_desk(self):
        self.assertEqual(self.client.get('/api/products').status_code,200);self.assertEqual(self.client.get('/api/admin/state').status_code,401)
    def test_csrf_required(self):self.assertEqual(self.client.post('/api/checkout',json={}).status_code,403)
    def test_order_requires_token(self):self.assertEqual(self.client.get('/api/order').status_code,401)
    def test_admin_login_and_product(self):
        result=self.post('/api/admin/login',{'username':'admin','password':'browser-test-password'});self.assertEqual(result.status_code,200);self.csrf=result.json['csrf']
        self.assertEqual(self.post('/api/admin/products',dict(name='Cup',sku='X',description='Nice',category='Table',price_cents=100,stock=1)).status_code,201)
    def test_contact_data_not_public(self):
        store.save_product(self.path,dict(name='Cup',sku='X',description='Nice',category='Table',price_cents=100,stock=1))
        result=self.post('/api/checkout',dict(idempotency_key='http-checkout-001',name='Private name',email='private@example.org',items=[{'product_id':1,'quantity':1}]))
        self.assertEqual(result.status_code,201);self.assertNotIn('private@example.org',str(result.json))
        response=self.client.get('/api/order',headers={'Authorization':'Bearer '+result.json['token']});self.assertEqual(response.status_code,200);self.assertEqual(response.headers['Cache-Control'],'no-store')
    def test_customer_action_cannot_override_cancel(self):
        self.assertEqual(self.post('/api/order/cancel',{'action':'pay'}).status_code,403)
    def test_wrong_json_shape(self):self.assertEqual(self.post('/api/checkout',[]).status_code,400)
