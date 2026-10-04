import paramiko, time, re
import sys
sys.stdout.reconfigure(encoding='utf-8')

HOST = "10.255.11.254"
USER = "uniwai11"
PWD = "GbypPRuuyds"
POD = "physics-tutor-74b5558965-gj6qm"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PWD, timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8','replace').strip(), stderr.read().decode('utf-8','replace').strip()

def clean(s):
    return re.sub(r'\x1b\[[0-9;]*[mGKlh]|\[K|\[A|\[1G|\[\?[0-9]+[lh]', '', s)

# Verify librosa IS installed
print("=== librosa location ===")
out, _ = run("kubectl exec " + POD + " -- python3 -c 'import librosa; print(librosa.__file__)'")
print(out)

# The app runs as PID 1 via the init script which does:
# python3 app.py  (without setting PYTHONPATH to include /tmp/.local)
# We need to install librosa into the SYSTEM python (opt/conda) instead
print("\n=== Installing librosa into /opt/conda (system-wide, no --user) ===")
out, err = run(
    "kubectl exec " + POD + " -- /opt/conda/bin/pip install -q librosa numba resampy soundfile 2>&1 | tail -5",
    timeout=180
)
print(out or err[:300])

print("\n=== Verify system python has librosa ===")
out, _ = run("kubectl exec " + POD + " -- python3 -c 'import librosa; print(\"OK\", librosa.__version__, librosa.__file__)'")
print(out)

print("\n=== Verify cv2 ===")
out, _ = run("kubectl exec " + POD + " -- python3 -c 'import cv2; print(\"cv2 OK\", cv2.__version__)'")
print(out)

print("\n=== Test full Wav2Lip import chain ===")
out, err = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import sys\n"
    "sys.path.insert(0, '/workspace/physics_tutor/Wav2Lip')\n"
    "import scipy, cv2, os, argparse\n"
    "import audio\n"
    "print('ALL IMPORTS OK')\n"
    "\""
)
print(out or err[:300])

# Ollama status
print("\n=== Ollama pull status ===")
out, _ = run("kubectl exec " + POD + " -- tail -1 /tmp/pull.log 2>&1")
print(clean(out))

out, _ = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import urllib.request, json\n"
    "try:\n"
    "    r = urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)\n"
    "    data = json.loads(r.read())\n"
    "    names = [m['name'] for m in data.get('models', [])]\n"
    "    print('Models:', names)\n"
    "except Exception as e: print('Ollama:', e)\n"
    "\""
)
print(out)

client.close()
print("\nDone!")
