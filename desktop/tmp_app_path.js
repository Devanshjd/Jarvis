const { app } = require('electron');
app.whenReady().then(() => {
  console.log('appPath=', app.getAppPath());
  console.log('cwd=', process.cwd());
  app.quit();
});
