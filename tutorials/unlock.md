# Unlocking a Stock Game & Watch Device

If you prefer a video tutorial, [here's a terse tutorial on device unlocking](https://www.youtube.com/watch?v=VIfEMVrW9GU).

To unlock your device, just run the following single command and follow the onscreen instructions.
```bash
gnwmanager unlock
```


A typical complete unlocking output will look like:
```text
$ gnwmanager unlock

If interrupted, resume unlocking with:
    gnwmanager unlock --backup-dir=backups-2023-10-25-12-49-51

Detected MARIO game and watch.
Backing up itcm to "backups-2023-10-25-12-49-51/itcm_backup_mario.bin"... complete!
Backing up external flash to "backups-2023-10-25-12-49-51/flash_backup_mario.bin"... complete!
Flashing payload to external flash... complete!


Payload successfully flashed. Perform the following steps:

1. Fully remove power, then re-apply power.
2. Press the power button to turn on the device; the screen should turn blue.

Press the "enter" key when the screen is blue:
Backing up internal flash to "backups-2023-10-25-12-49-51/internal_flash_backup_mario.bin"... complete!
Unlocking device... complete!
Restoring firmware... complete!
Unlocking complete!
Pressing the power button should launch the original firmware.
```
