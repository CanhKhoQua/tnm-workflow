const path = require('path');

module.exports = {
  apps: [
    {
      name: 'tnm-workflow-5000',
      cwd: __dirname,
      script: 'start.cjs',
      interpreter: 'node',
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONPATH: path.join(__dirname, 'scripts'),
      },
    },
  ],
};
