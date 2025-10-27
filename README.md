# Viwoods Sync Tool

A Python command-line tool to sync notes and files from a Viwoods e-ink tablet to a local directory.


<a href="https://buymeacoffee.com/farsonic" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px; width: 217px;" ></a>


This tool connects to the tablet's local file transfer service, recursively scans the folder structure, and downloads files. It uses a local SQLite database (`.sync_db.sqlite`) to track file metadata (update time, size) and only downloads new or modified files, making subsequent syncs much faster.


[![Watch the video](https://img.youtube.com/vi/I53uKuBrpG0/hqdefault.jpg)](https://www.youtube.com/embed/I53uKuBrpG0)



## Features

* **Recursive Sync:** Downloads the entire folder structure from the tablet.
* **Delta Syncing:** Tracks synced files and only downloads new or modified files.
* **Targeted Sync:** Choose to sync all root folders (`--all`) or only specific sub-folders (`--folder`).
* **Force Sync:** A `--force` flag allows you to clear the local cache and re-download all files.

## Installation

1.  Clone this repository:
    ```bash
    git clone [https://github.com/your-username/viwoods-sync.git](https://github.com/your-username/viwoods-sync.git)
    cd viwoods-sync
    ```

2.  Create and activate a Python virtual environment:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

You must provide the IP address of your Viwoods tablet. You can find this when you use the WLAN Transfer option where the 
IP Address is shown. You don't need to specify the port. If you want to restore a lost .note file use the WALN Transfer web
page to upload it. 

```bash
python3 viwoods_sync.py <ip_address> [options]
