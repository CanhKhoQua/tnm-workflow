const { spawn } = require('child_process');
const proc = spawn('python', ['scripts/webapp/app.py'], {
  cwd: __dirname, stdio: 'inherit', windowsHide: true,
});
proc.on('close', (code) => process.exit(code));
