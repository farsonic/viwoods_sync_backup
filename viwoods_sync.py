#!/usr/bin/env python3
"""
Viwoods Sync Tool - WORKING VERSION
Syncs entire folder structure from Viwoods tablet to local directory
Tracks changes and only downloads new/modified files

FIXED: Uses correct 3-step download process:
1. getChildFolderList - get noteId
2. packageFile - get file path
3. /download - actually download the file
"""

import requests
import json
import argparse
from pathlib import Path
from datetime import datetime
import hashlib
import sqlite3

class ViwoodsSync:
    def __init__(self, ip: str = "192.168.0.130", port: int = 8090, local_dir: str = "./viwoods_sync"):
        self.base_url = f"http://{ip}:{port}"
        self.session = requests.Session()
        self.local_dir = Path(local_dir)
        self.local_dir.mkdir(exist_ok=True)

        # SQLite database to track synced files
        self.db_path = self.local_dir / ".sync_db.sqlite"
        self.init_database()

    def init_database(self):
        """Initialize SQLite database to track synced files"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS synced_files (
                file_path TEXT PRIMARY KEY,
                note_id TEXT,
                update_time INTEGER,
                file_size INTEGER,
                last_sync TEXT,
                checksum TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def list_folder(self, app_type: str, folder_name: str, folder_id: str = None):
        """List contents of a folder"""
        url = f"{self.base_url}/getChildFolderList"
        params = {
            'appType': app_type,
            'folderName': folder_name,
            'language': 'en'
        }
        if folder_id:
            params['folderId'] = folder_id

        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 200:
                    return data.get('data', [])
        except Exception as e:
            print(f"Error listing folder: {e}")
        return []

    def download_file(self, file_name: str, note_id: str, folder_id: str,
                     app_type: str, local_path: Path) -> bool:
        """
        Download a file from Viwoods using the correct 3-step process:
        1. packageFile - get the file path on tablet
        2. /download - actually download the file content
        
        IMPORTANT: note_id is from getChildFolderList, NOT the filename!
        """
        # Ensure .note extension
        if not file_name.endswith('.note'):
            file_name_with_ext = f"{file_name}.note"
        else:
            file_name_with_ext = file_name

        try:
            # Step 1: packageFile to get the file path on the tablet
            url = f"{self.base_url}/packageFile"
            params = {
                'appType': app_type,
                'fileUrl': note_id,  # CRITICAL: This is the noteId, not the filename!
                'fileFormat': 'note',
                'fileName': file_name_with_ext,
                'folderId': folder_id,
                'isFolder': 'false',
                'childFileFormat': 'note'
            }

            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                return False
            
            data = response.json()
            if data.get('code') != 200:
                return False
            
            file_path = data.get('data')
            if not file_path or not isinstance(file_path, str):
                return False

            # Step 2: Use /download endpoint with the file path to get actual content
            download_url = f"{self.base_url}/download"
            download_params = {'filePath': file_path}
            
            response = self.session.get(download_url, params=download_params, timeout=60, stream=True)
            
            if response.status_code != 200:
                return False

            # Ensure parent directory exists
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Verify we got something
            if local_path.stat().st_size == 0:
                local_path.unlink()
                return False
                
            return True
            
        except Exception as e:
            return False

    def calculate_checksum(self, file_path: Path) -> str:
        """Calculate MD5 checksum of a file"""
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return md5.hexdigest()

    def is_file_synced(self, remote_path: str, update_time: int) -> bool:
        """Check if file is already synced and up to date"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT update_time FROM synced_files WHERE file_path = ?
        ''', (remote_path,))

        result = cursor.fetchone()
        conn.close()

        if result:
            return result[0] >= update_time
        return False

    def record_sync(self, remote_path: str, note_id: str, update_time: int,
                    file_size: int, local_path: Path):
        """Record a successful sync in the database"""
        checksum = self.calculate_checksum(local_path)
        now = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO synced_files
            (file_path, note_id, update_time, file_size, last_sync, checksum)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (remote_path, note_id, update_time, file_size, now, checksum))

        conn.commit()
        conn.close()

    def sync_folder_recursive(self, app_type: str, folder_name: str, folder_id: str,
                             local_path: Path, path_stack: list, stats: dict):
        """Recursively sync a folder and all its contents"""

        # Create local directory
        local_path.mkdir(parents=True, exist_ok=True)

        # Get folder contents
        items = self.list_folder(app_type, folder_name, folder_id)

        if not items:
            return

        for item in items:
            item_name = item.get('fileName', 'Unknown')
            is_folder = item.get('isFolder', False)
            note_id = item.get('noteId', '')
            update_time = item.get('updateTime', 0)

            if is_folder:
                # Recursively sync subfolder
                stats['folders'] += 1
                print(f"📁 {'/'.join(path_stack)}/{item_name}")

                self.sync_folder_recursive(
                    app_type,
                    item_name,
                    note_id,
                    local_path / item_name,
                    path_stack + [item_name],
                    stats
                )
            else:
                # Sync file
                file_name = item_name if item_name.endswith('.note') else f"{item_name}.note"
                local_file_path = local_path / file_name

                # Build a unique identifier for tracking
                remote_identifier = f"{app_type}/{folder_id}/{note_id}/{file_name}"

                if self.is_file_synced(remote_identifier, update_time) and local_file_path.exists():
                    file_size = local_file_path.stat().st_size
                    print(f"  ⊙ {file_name} ({file_size:,} bytes - cached)")
                    stats['skipped'] += 1
                else:
                    print(f"  ↓ {file_name}", end='', flush=True)

                    if self.download_file(item_name, note_id, folder_id, app_type, local_file_path):
                        file_size = local_file_path.stat().st_size
                        
                        self.record_sync(remote_identifier, note_id, update_time,
                                       file_size, local_file_path)
                        print(f" → ✓ {file_size:,} bytes")
                        stats['downloaded'] += 1
                    else:
                        print(f" → ✗ failed")
                        stats['failed'] += 1

    def sync_all(self, include_all: bool = False):
        """Sync entire Viwoods structure"""
        print("=" * 70)
        print("🔄 Viwoods Sync Starting")
        print("=" * 70)
        print(f"Local directory: {self.local_dir.absolute()}")
        print(f"Tablet: {self.base_url}")

        # Default folders to sync (unless --all is specified)
        default_folders = ['Paper', 'Daily', 'Meeting', 'Memo']

        if include_all:
            print("Mode: Syncing ALL folders")
        else:
            print(f"Mode: Syncing {', '.join(default_folders)} (use --all for everything)")
        print()

        stats = {
            'folders': 0,
            'downloaded': 0,
            'skipped': 0,
            'failed': 0
        }

        start_time = datetime.now()

        # Get root folders
        root_items = self.list_folder('root', 'Home', '')

        for root_item in root_items:
            root_name = root_item.get('fileName', 'Unknown')
            app_type = root_item.get('appType', 'APP_PAPER')

            # Skip if not in default list (unless --all flag is set)
            if not include_all and root_name not in default_folders:
                print(f"⊘ Skipping: {root_name} (not in default sync list)")
                continue

            print(f"\n📂 {root_name}")
            print("-" * 70)

            # Sync this root folder and all subfolders
            self.sync_folder_recursive(
                app_type,
                root_name,
                '',
                self.local_dir / root_name,
                [root_name],
                stats
            )

        # Summary
        elapsed = (datetime.now() - start_time).total_seconds()

        print("\n" + "=" * 70)
        print("✅ Sync Complete!")
        print("=" * 70)
        print(f"Folders processed: {stats['folders']}")
        print(f"Files downloaded:  {stats['downloaded']}")
        print(f"Files skipped:     {stats['skipped']}")
        print(f"Files failed:      {stats['failed']}")
        print(f"Time elapsed:      {elapsed:.1f}s")
        print(f"\nLocal directory:   {self.local_dir.absolute()}")
        print("=" * 70)

    def sync_folder(self, folder_path: str):
        """Sync a specific folder only (e.g., 'Paper/Papers/Unclassified Notes')"""
        parts = folder_path.split('/')

        if not parts:
            print("Invalid folder path")
            return

        print("=" * 70)
        print(f"🔄 Syncing: {folder_path}")
        print("=" * 70)

        stats = {
            'folders': 0,
            'downloaded': 0,
            'skipped': 0,
            'failed': 0
        }

        # Navigate to the folder
        # First get root to determine app_type
        root_name = parts[0]
        root_items = self.list_folder('root', 'Home', '')

        app_type = None
        for item in root_items:
            if item.get('fileName') == root_name:
                app_type = item.get('appType')
                break

        if not app_type:
            print(f"Root folder not found: {root_name}")
            return

        # Navigate through the path
        current_folder_id = None
        current_items = []

        for i, folder_name in enumerate(parts):
            if i == 0:
                # First level - use root
                current_items = self.list_folder(app_type, folder_name, '')
            else:
                # Find the folder in current items
                found = False
                for item in current_items:
                    if item.get('fileName') == folder_name and item.get('isFolder'):
                        current_folder_id = item.get('noteId')
                        current_items = self.list_folder(app_type, folder_name, current_folder_id)
                        found = True
                        break

                if not found:
                    print(f"Folder not found: {folder_name}")
                    return

        # Now sync this folder
        local_path = self.local_dir / folder_path

        self.sync_folder_recursive(
            app_type,
            parts[-1],
            current_folder_id or '',
            local_path,
            parts,
            stats
        )

        print("\n" + "=" * 70)
        print("✅ Sync Complete!")
        print("=" * 70)
        print(f"Files downloaded: {stats['downloaded']}")
        print(f"Files skipped:    {stats['skipped']}")
        print(f"Files failed:     {stats['failed']}")

def main():
    parser = argparse.ArgumentParser(
        description='Sync Viwoods notes to local directory',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync default folders (Paper, Daily, Meeting, Memo)
  %(prog)s 192.168.0.130

  # Sync ALL folders including Learning and Picking
  %(prog)s 192.168.0.130 --all

  # Sync to specific directory
  %(prog)s 192.168.0.130 --output ~/Documents/Viwoods

  # Sync only a specific folder
  %(prog)s 192.168.0.130 --folder "Paper/Papers/Unclassified Notes"

  # Force re-download everything (ignore sync database)
  %(prog)s 192.168.0.130 --force
        """
    )

    parser.add_argument('ip', help='IP address of Viwoods tablet')
    parser.add_argument('--port', type=int, default=8090, help='Port (default: 8090)')
    parser.add_argument('--output', '-o', default='./viwoods_sync',
                       help='Local output directory (default: ./viwoods_sync)')
    parser.add_argument('--folder', '-f', help='Sync only specific folder (e.g., "Paper/Papers")')
    parser.add_argument('--all', action='store_true',
                       help='Sync ALL folders (default: only Paper, Daily, Meeting, Memo)')
    parser.add_argument('--force', action='store_true',
                       help='Force re-download all files (ignore sync database)')

    args = parser.parse_args()

    # Create syncer
    syncer = ViwoodsSync(args.ip, args.port, args.output)

    # Clear database if force sync
    if args.force:
        print("⚠️  Force mode: clearing sync database")
        syncer.db_path.unlink(missing_ok=True)
        syncer.init_database()

    # Sync
    if args.folder:
        syncer.sync_folder(args.folder)
    else:
        syncer.sync_all(include_all=args.all)

if __name__ == '__main__':
    main()
