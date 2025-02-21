# Installing GnwManager
GnWManager is easy to install, and it generally just installed like any python package.
Like other python-based CLI tools, it's best to install with `pipx`.
This tutorial breaks it up by operating system in case you are really starting from scratch.

## Windows
<details>
  <summary>Click to expand.</summary>

  ### Installing Chocolately
  [Chocolately](https://chocolatey.org/) is a package manager for Windows.
  A package manager streamlines the installation and updating of software.
  Think of it like a CLI-based app store.

  To install Chocolately, [follow their install instructions](https://chocolatey.org/install).

  To summarize their installation instructions, open PowerShell with "Run as administrator" and run the following command.

  ```powershell
  Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
  ```

  ### Installing python
  If you don't have a modern (>=3.9) version of python installed, you can install it with `Chocolately`:

  ```bash
  choco install python
  ```

  Proceed to the [common section](#Common) for remaining installation instructions.

</details>

## MacOS
<details>
  <summary>Click to expand.</summary>

  #### Installing Homebrew
  [Homebrew](https://brew.sh/) is a package manager for MacOS.
  A package manager streamlines the installation and updating of software.
  Think of it like a CLI-based app store.

  To install Homebrew, [follow their install instructions](https://brew.sh/).

  To summarize their installation instructions, run the following command in a terminal.
  ```bash
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ```

  #### Installing python
  If you don't have a modern (>=3.9) version of python installed, you can install it with `brew`:

  ```bash
  brew install python
  ```

  Proceed to the [common section](#Common) for remaining installation instructions.

</details>

## Linux (Debian/Ubuntu)

<details>
  <summary>Click to expand.</summary>

  #### Installing python
  If you don't have a modern (>=3.9) version of python installed, you can install it with `apt-get`:

  ```bash
  sudo apt-get update
  sudo apt-get install python
  ```

  Proceed to the [common section](#Common) for remaining installation instructions.

</details>

## Common
#### Installing pipx
[Install pipx, following the instructions on its website.](<https://pipx.pypa.io/stable/#install-pipx>)

#### Installing gnwmanager
GnWManager can now be installed with pipx:

```bash
pipx install gnwmanager
```

#### Installing third-party gnwmanager dependencies
GnWManager depends on OpenOCD to handle debugger-probe communications.
GnWManager offers a crossplatform way of installing openocd:

```bash
gnwmanager install openocd
```

## Updating
As of version ``v0.5.0``, GnWManager provides the command ``gnwmanager upgrade`` to update
itself.

Alternatively, update GnWManager as you would any python command line tool installed by `pipx`:
```bash
pipx upgrade gnwmanager
```
