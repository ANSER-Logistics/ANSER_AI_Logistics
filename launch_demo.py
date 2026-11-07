import os
import shutil
import subprocess
import sys
import threading
import time

import nest_asyncio
import pyngrok.installer

pyngrok.installer.install_ngrok = lambda *args, **kwargs: None
from pyngrok import conf, ngrok

nest_asyncio.apply()

def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

def vram_monitor_thread(project_root):
    """
    Background thread to monitor VRAM usage.
    If VRAM > 90%, it generates an artifact alert.
    """
    try:
        import torch
    except ImportError:
        return

    alert_file = os.path.join(project_root, "VRAM_Alert.md")
    while True:
        try:
            if torch.cuda.is_available():
                # NGUONG DAT TREN `reserved`, KHONG phai `allocated`.
                #
                # Ban truoc tinh CA HAI roi chi dung `allocated` — ruff bao
                # F841 cho bien khong dung, nhung thu dang ke hon la mot loi DO
                # LUONG trong chinh thu lam nhiem vu canh bao:
                #
                #   allocated = bo nho cac tensor DANG giu
                #   reserved  = bo nho PyTorch da xin cua driver va GIU LAI
                #
                # Bo cap phat co dem cua PyTorch khong tra lai driver khi mot
                # tensor duoc giai phong, nen `reserved` >= `allocated`, thuong
                # lon hon nhieu. Thu gay OOM la `reserved`. Canh bao theo
                # `allocated` bao MUON, hoac khong bao gi trong khi tien trinh
                # da sat tran driver.
                allocated = torch.cuda.memory_allocated()
                reserved = torch.cuda.memory_reserved()
                max_memory = torch.cuda.get_device_properties(0).total_memory
                if max_memory > 0:
                    percent_used = (reserved / max_memory) * 100
                    percent_alloc = (allocated / max_memory) * 100
                    if percent_used > 90.0:
                        # Ghi CA HAI con so: khoang cach giua chung cho biet nen
                        # goi `empty_cache()` hay that su phai ha tai.
                        with open(alert_file, "w", encoding="utf-8") as f:
                            f.write(
                                "# VRAM CRITICAL ALERT" + chr(10) * 2
                                + f"reserved {percent_used:.1f}% cua tong VRAM "
                                + f"(allocated {percent_alloc:.1f}%)." + chr(10)
                                + "Vuot nguong 90%. Fallback mechanism triggered."
                            )
                        print(
                            f"[ALERT] VRAM reserved {percent_used:.1f}% "
                            f"(allocated {percent_alloc:.1f}%)"
                        )
        except Exception as loi:
            # KHONG `pass` tran (AGENTS §4.1 quy tac 4). Day la mot WATCHDOG:
            # nuot im lang nghia la no van chay, van trong nhu dang canh gioi,
            # ma khong bao gio bao gi. Vi du that: may khong co device 0 thi
            # `get_device_properties(0)` nem, va vong lap quay mai vo ich.
            print(f"[watchdog] khong doc duoc VRAM: {loi}")
        time.sleep(10)

def main():
    print("Setting up Project A demo environment...")
    # This gets the folder where 'launch_demo.py' actually lives
    project_root = os.path.dirname(os.path.abspath(__file__))
    print(f"Project root detected: {project_root}")

    # Start VRAM monitor
    monitor = threading.Thread(target=vram_monitor_thread, args=(project_root,), daemon=True)
    monitor.start()

    # 2. PREPARE ENVIRONMENT
    env = os.environ.copy()
    env["DATABASE_URL"] = _require_env("DATABASE_URL")

    # CRITICAL FIX: Add project_root to PYTHONPATH
    # This tells Python/Uvicorn: "Look for modules in this folder first"
    env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")
    env["VLLM_WORKER_MULTIPROC_METHOD"] = "spawn"

    # 3. INSTALL DRIVERS (If missing)
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        print("Installing psycopg2-binary...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])

    ngrok_path = shutil.which("ngrok")
    if ngrok_path:
        conf.get_default().ngrok_path = ngrok_path

    ngrok_token = os.getenv("NGROK_AUTHTOKEN", "").strip()
    if ngrok_token:
        ngrok.set_auth_token(ngrok_token)

    try:
     public_url = ngrok.connect(8000).public_url
     print("\n==================================================================")
     print(f"PUBLIC URL: {public_url}")
     print("==================================================================\n")
    except Exception as e:
     print(f"Ngrok error: {e}")

    # 4. LAUNCH UVICORN
    # We remove '--reload' for Colab stability (it causes multiprocessing issues in notebooks)
    cmd = [
        "uvicorn",
        "src.api.main:app",
        "--host", "0.0.0.0",
        "--port", "8000"
    ]

    print(f"Executing server in: {project_root}")

    # We pass 'cwd=project_root' to ensure Uvicorn runs INSIDE the correct folder
    subprocess.run(cmd, cwd=project_root, env=env)

if __name__ == "__main__":
    main()
