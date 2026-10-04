import paramiko, time, re, json
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

# Check Ollama pull progress
print("=== Ollama pull progress ===")
out, _ = run(f"kubectl exec {POD} -- tail -1 /tmp/pull.log 2>&1")
print(clean(out))

# Check Ollama server
out, err = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import urllib.request, json\n"
    "try:\n"
    "    r = urllib.request.urlopen('http://localhost:11434/api/version', timeout=2)\n"
    "    print('UP')\n"
    "except: print('DOWN')\n"
    "\""
)
print("Ollama server:", out)

# THE CRITICAL TEST: send a real WS message to the running app via curl-like HTTP
# Since we can't do WS from here, test via app's own python3 that imports the modules
print("\n=== Test: does the running app see librosa? ===")
# The app logs when wav2lip runs. Let's send a text message via websockets
# Instead, check what imports succeeded at app startup via logs
out, _ = run(f"kubectl logs {POD} --tail=30 2>&1")
print(out)

# Check if wav2lip_lipsync can be imported by the app process (pid 1)
# by running a child process from within the pod the same way app.py would
print("\n=== Direct test of wav2lip (no shell wrapper) ===")
out, err = run(
    "kubectl exec " + POD + " -- python3 /workspace/physics_tutor/app.py --test 2>&1 || "
    "kubectl exec " + POD + " -- python3 -c \""
    "import sys\n"
    "sys.path.insert(0, '/tmp/.local/lib/python3.10/site-packages')\n"
    "sys.path.insert(0, '/workspace/physics_tutor')\n"
    "sys.path.insert(0, '/workspace/physics_tutor/Wav2Lip')\n"
    "import librosa\n"
    "import cv2\n"
    "import audio\n"
    "print('ALL OK - librosa', librosa.__version__)\n"
    "\"",
    timeout=20
)
print(out or err[:400])

client.close()
