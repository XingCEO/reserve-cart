const { defineConfig }=require('@playwright/test');
module.exports=defineConfig({testDir:'tests/browser',workers:1,fullyParallel:false,use:{baseURL:'http://127.0.0.1:5056',viewport:{width:1440,height:1000},trace:'retain-on-failure'},webServer:{command:`${process.env.PYTHON||'python3'} tests/serve_browser.py`,url:'http://127.0.0.1:5056',reuseExistingServer:false,timeout:30000}});
