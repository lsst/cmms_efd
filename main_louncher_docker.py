#!/usr/bin/env python3
import subprocess
import os
import sys
import time


def main() -> None:
    """
    Launches both the backend process and the NiceGUI interface simultaneously.

    This function starts two subprocesses:
    1. The backend logic located in `backend/main.py`.
    2. The NiceGUI interface located in `U_I/CDIAT_UI.py`.

    Both processes are monitored continuously. If one of them stops or
    a KeyboardInterrupt (SIGINT) is received, all subprocesses are terminated.
    """
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    procs = []

    try:
        backend_proc = subprocess.Popen(
            ["python", "backend/main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        procs.append(("BACKEND", backend_proc))
        print(f"Backend started pid={backend_proc.pid}")

        ui_proc = subprocess.Popen(
            ["python", "U_I/CDIAT_UI.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        procs.append(("NICEGUI", ui_proc))
        print(f"NiceGUI started pid={ui_proc.pid}")

        while True:
            for name, p in procs:
                if p.stdout:
                    line = p.stdout.readline()
                    if line:
                        print(f"[{name}] {line}", end="")

            if all(p.poll() is not None for _, p in procs):
                print("Both processes have finished. Exiting...")
                break

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("SIGINT received, terminating processes...")
    finally:
        for name, p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        sys.exit(0)


if __name__ == "__main__":
    main()
