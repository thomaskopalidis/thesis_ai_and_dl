import paramiko, time, re
import sys, os
sys.stdout.reconfigure(encoding='utf-8')

HOST = "10.255.11.254"
USER = "uniwai11"
PWD = "GbypPRuuyds"
POD = "physics-tutor-74b5558965-gj6qm"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PWD, timeout=30)
sftp = client.open_sftp()

def run(cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8','replace').strip(), stderr.read().decode('utf-8','replace').strip()

def clean(s):
    return re.sub(r'\x1b\[[0-9;]*[mGKlh]|\[K|\[A|\[1G|\[\?[0-9]+[lh]', '', s)

os.chdir(r"c:\Users\thoma\Desktop\AI and DL\Thesis_ai_and_dl")

# Upload files
files = [
    ("app.py",                  "/home/uniwai11/physics_tutor/app.py"),
    ("core/wav2lip_lipsync.py", "/home/uniwai11/physics_tutor/core/wav2lip_lipsync.py"),
    ("core/llm.py",             "/home/uniwai11/physics_tutor/core/llm.py"),
    ("frontend/index.html",     "/home/uniwai11/physics_tutor/frontend/index.html"),
    ("frontend/main.js",        "/home/uniwai11/physics_tutor/frontend/main.js"),
]
print("Uploading...")
for local, server in files:
    sftp.put(local, server)
    pod_path = server.replace("/home/uniwai11", "/workspace")
    run(f"kubectl cp {server} {POD}:{pod_path}")
    print(f"  {local} OK")
sftp.close()

# Find uvicorn/app port holder and kill just that process
# PID 1 is the init script; the actual python3 app.py is a child of it
print("\nFinding app process...")
out, _ = run(f"kubectl exec {POD} -- ps -ef 2>&1")
print(out[:600])

# Kill port 8000 holder without touching PID 1
print("\nKilling uvicorn on port 8000...")
run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import subprocess, signal, os\n"
    "# find process holding :8000\n"
    "r = subprocess.run(['ss', '-tlnp'], capture_output=True, text=True)\n"
    "for line in r.stdout.splitlines():\n"
    "    if '8000' in line and 'pid=' in line:\n"
    "        pid = line.split('pid=')[1].split(',')[0]\n"
    "        if pid != '1':\n"
    "            os.kill(int(pid), signal.SIGTERM)\n"
    "            print('Killed PID', pid)\n"
    "            break\n"
    "else:\n"
    "    print('No process on 8000 found via ss')\n"
    "\"",
    timeout=10
)
time.sleep(2)

# Start new app in background
print("Starting new app...")
run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import subprocess, os\n"
    "env = dict(os.environ)\n"
    "env['OLLAMA_MODELS'] = '/tmp/ollama_models'\n"
    "env['HOME'] = '/tmp'\n"
    "env['PATH'] = '/tmp/bin:/tmp/.local/bin:' + env.get('PATH','')\n"
    "env['PYTHONPATH'] = '/tmp/.local/lib/python3.10/site-packages:/workspace/physics_tutor:' + env.get('PYTHONPATH','')\n"
    "log = open('/tmp/app_new.log', 'w')\n"
    "p = subprocess.Popen(\n"
    "    ['python3', '/workspace/physics_tutor/app.py'],\n"
    "    env=env, stdout=log, stderr=log\n"
    ")\n"
    "print('Started PID:', p.pid)\n"
    "\"",
    timeout=10
)
time.sleep(12)

print("\nNew app log:")
out, _ = run(f"kubectl exec {POD} -- cat /tmp/app_new.log 2>&1")
print(out[:1000])

# Quick test: try to import librosa from within the running app's python
print("\nTest librosa import (same python):")
out, _ = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import sys\n"
    "sys.path.insert(0, '/tmp/.local/lib/python3.10/site-packages')\n"
    "sys.path.insert(0, '/workspace/physics_tutor')\n"
    "sys.path.insert(0, '/workspace/physics_tutor/Wav2Lip')\n"
    "import librosa, cv2\n"
    "import audio\n"
    "print('librosa', librosa.__version__, '| cv2', cv2.__version__, '| audio OK')\n"
    "\""
)
print(out)

client.close()
