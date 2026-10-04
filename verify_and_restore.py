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

# 1. Check new app.py top lines (sys.path fix)
print("=== app.py top (sys.path fix?) ===")
out, _ = run(f"kubectl exec {POD} -- head -10 /workspace/physics_tutor/app.py 2>&1")
print(out)

# 2. librosa via app's python
print("\n=== librosa accessible from app's python ===")
out, err = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import sys\n"
    "sys.path.insert(0, '/tmp/.local/lib/python3.10/site-packages')\n"
    "import librosa, cv2\n"
    "print('librosa', librosa.__version__, 'cv2', cv2.__version__)\n"
    "\""
)
print(out or err[:200])

# 3. Full wav2lip import test
print("\n=== Wav2Lip import test ===")
out, err = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import sys\n"
    "sys.path.insert(0, '/tmp/.local/lib/python3.10/site-packages')\n"
    "sys.path.insert(0, '/workspace/physics_tutor')\n"
    "from core.wav2lip_lipsync import generate_wav2lip_video\n"
    "print('wav2lip import OK')\n"
    "\"",
    timeout=20
)
print(out or err[:200])

# 4. Start Ollama server
print("\n=== Starting Ollama server ===")
out, _ = run("kubectl exec " + POD + " -- pgrep -x ollama 2>/dev/null && echo running || echo stopped")
if "running" not in out:
    run(
        "kubectl exec " + POD + " -- python3 -c \""
        "import subprocess, os\n"
        "env = dict(os.environ)\n"
        "env['OLLAMA_MODELS'] = '/tmp/ollama_models'\n"
        "env['HOME'] = '/tmp'\n"
        "env['PATH'] = '/tmp/bin:' + env.get('PATH', '')\n"
        "os.makedirs('/tmp/ollama_models', exist_ok=True)\n"
        "p = subprocess.Popen(['/tmp/bin/ollama', 'serve'], env=env,\n"
        "    stdout=open('/tmp/ollama.log', 'w'), stderr=subprocess.STDOUT)\n"
        "print('Ollama PID:', p.pid)\n"
        "\"",
        timeout=10
    )
    time.sleep(6)

# 5. Check model
out, _ = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import urllib.request, json\n"
    "try:\n"
    "    r = urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)\n"
    "    data = json.loads(r.read())\n"
    "    names = [m['name'] for m in data.get('models', [])]\n"
    "    print('Models:', names)\n"
    "except Exception as e: print('Ollama error:', e)\n"
    "\""
)
print("Ollama models:", out)

if "qwen" not in out.lower():
    print("Pulling model...")
    run(
        "kubectl exec " + POD + " -- python3 -c \""
        "import subprocess, os\n"
        "env = dict(os.environ)\n"
        "env['OLLAMA_MODELS'] = '/tmp/ollama_models'\n"
        "env['HOME'] = '/tmp'\n"
        "env['PATH'] = '/tmp/bin:' + env.get('PATH', '')\n"
        "p = subprocess.Popen(['/tmp/bin/ollama', 'pull', 'qwen2.5:14b-instruct-q4_K_M'],\n"
        "    env=env, stdout=open('/tmp/pull.log', 'w'), stderr=subprocess.STDOUT)\n"
        "print('Pull PID:', p.pid)\n"
        "\"",
        timeout=10
    )
    print("Model pull started (~12 min). Monitor: kubectl exec POD -- tail -f /tmp/pull.log")
else:
    print("Model ready!")

# 6. App log check
print("\n=== kubectl logs (last 15) ===")
out, _ = run(f"kubectl logs {POD} --tail=15 2>&1")
print(out)

client.close()
