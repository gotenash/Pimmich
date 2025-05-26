import subprocess
import psutil

def is_slideshow_running():
    for proc in psutil.process_iter(attrs=['cmdline']):
        try:
            if proc.info['cmdline'] and 'local_slideshow.py' in proc.info['cmdline']:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

def stop_slideshow():
    for proc in psutil.process_iter(attrs=['pid', 'cmdline']):
        try:
            if proc.info['cmdline'] and 'local_slideshow.py' in proc.info['cmdline']:
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

def start_slideshow():
    subprocess.Popen(["python3", "local_slideshow.py"])
