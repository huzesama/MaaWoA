# 📰News

If you purchased this program by paying, please request a refund immediately and report it. This project is free and open source.

## Android Background Mode Resolution Notes and FAQ

After stopping a task, switching the resolution and then starting the task may cause recognition failures due to leftover cache issues. The cache depends on the Agent service, and the Agent is only initialized when MaaWoA starts.
After switching the background mode resolution, close MaaWoA and its background processes first, then restart.

## Desktop Foreground Controller Notes and FAQ

1. The foreground controller completely occupies the foreground during operation. Manual operation at this time will interfere with the normal execution of the script, so it is not recommended to open other software at the same time.
2. The screenshot function directly captures the current foreground window. Therefore, no obstructions may appear in the screenshot, such as frame rate displays, ad pop-ups, Windows activation watermarks, etc.; otherwise, recognition will be affected.

## License

- This software is under [GNU Affero General Public License v3.0 (AGPL-3.0)](https://github.com/huzesama/MaaWoA/blob/main/LICENSE)
