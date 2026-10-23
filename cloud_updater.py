import os
import sys
import json
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_VERSION_FILE = os.path.join(BASE_DIR, "version.json")
CONFIG_FILE = os.path.join(BASE_DIR, "updater_config.json")

def get_updater_config():
    default_cfg = {
        "enabled": True,
        # This will be pointing to your deployed Render URL or GitHub Raw URL
        "update_url": "https://khs-billing.onrender.com/api/system/version",
        "base_download_url": "https://khs-billing.onrender.com/static/"
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return default_cfg

def get_local_version():
    if os.path.exists(LOCAL_VERSION_FILE):
        try:
            with open(LOCAL_VERSION_FILE, "r") as f:
                return json.load(f).get("version", "1.0.0")
        except:
            pass
    return "1.0.0"

def check_and_apply_update():
    cfg = get_updater_config()
    if not cfg.get("enabled"):
        return False, "Auto-updates disabled in config."

    update_url = cfg.get("update_url")
    if not update_url:
        return False, "No update URL configured."

    local_ver = get_local_version()
    print(f"[UPDATER] Current version: v{local_ver}")
    print("[UPDATER] Checking cloud server for updates...")

    try:
        # Fast timeout (3s) so it never hangs if internet is down or slow
        res = requests.get(update_url, timeout=3.5)
        if res.status_code != 200:
            return False, f"Server returned status {res.status_code}"

        remote_info = res.json()
        remote_ver = remote_info.get("version")
        files_to_update = remote_info.get("files", [])

        if not remote_ver or remote_ver == local_ver:
            print("[UPDATER] You are on the latest version.")
            return True, "Up to date"

        print(f"[UPDATER] >>> New version found: v{remote_ver}! Downloading updates...")

        base_dl = cfg.get("base_download_url", "").rstrip("/")
        downloaded = 0

        for filename in files_to_update:
            # SAFETY GUARD: Never allow database or credentials to be updated/overwritten!
            if any(forbidden in filename.lower() for forbidden in [".db", "token", "client_secret", "service_account", "cloud_sync_config"]):
                continue

            file_url = f"{base_dl}/{filename}"
            target_path = os.path.join(BASE_DIR, filename)

            try:
                f_res = requests.get(file_url, timeout=5)
                if f_res.status_code == 200 and len(f_res.content) > 10:
                    # Write to temporary file first to guarantee atomic write
                    temp_path = target_path + ".tmp"
                    with open(temp_path, "wb") as f:
                        f.write(f_res.content)
                    
                    # Replace existing file
                    if os.path.exists(target_path):
                        os.replace(temp_path, target_path)
                    else:
                        os.rename(temp_path, target_path)
                    
                    downloaded += 1
                    print(f"  + Updated: {filename}")
            except Exception as fe:
                print(f"  ! Failed to download {filename}: {fe}")

        # Update local version.json
        with open(LOCAL_VERSION_FILE, "w") as f:
            json.dump(remote_info, f, indent=2)

        print(f"[UPDATER] Successfully updated {downloaded} files to v{remote_ver}!")
        return True, f"Updated to {remote_ver}"

    except Exception as e:
        # Silent fail / offline pass-through
        print(f"[UPDATER] Skipping update (Offline or unreachable): {e}")
        return False, str(e)

if __name__ == "__main__":
    check_and_apply_update()
