"""
Full setup: download ollama binary, start server, pull model, monitor.
Runs everything in sequence keeping the SSH connection alive.
"""
import paramiko, time, sys, re
sys.stdout.reconfigure(encoding='utf-8')

HOST = "10.255.11.254"
USER = "uniwai11"
PWD = "GbypPRuuyds"
POD = "physics-tutor-74b5558965-gj6qm"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PWD, timeout=30)

def run(cmd, timeout=60):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8','replace').strip()
    err = stderr.read().decode('utf-8','replace').strip()
    return out, err

def clean(s):
    return re.sub(r'\x1b\[[0-9;]*[mGKlh]|\[K|\[A|\[1G|\[\?[0-9]+[lh]', '', s)

# ── 1. Check binary ──────────────────────────────────────────────────────────
out, _ = run(f"kubectl exec {POD} -- ls -lh /tmp/bin/ollama 2>&1")
print("Binary check:", out)

if "No such file" in out or not out.strip():
    print("Downloading Ollama binary (~375MB)...")
    # Use background download so we can monitor
    out, err = run(
        "kubectl exec " + POD + " -- python3 -c \""
        "import urllib.request, os\n"
        "os.makedirs('/tmp/bin', exist_ok=True)\n"
        "url = 'https://github.com/ollama/ollama/releases/download/v0.6.5/ollama-linux-amd64'\n"
        "urllib.request.urlretrieve(url, '/tmp/bin/ollama')\n"
        "import stat\n"
        "os.chmod('/tmp/bin/ollama', stat.S_IRWXU|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH|stat.S_IXOTH)\n"
        "size = os.path.getsize('/tmp/bin/ollama')\n"
        "print('DONE size=', size)\n"
        "\"",
        timeout=300
    )
    print("Download result:", out or err[:300])
    if "DONE" not in out:
        print("ERROR: download failed")
        client.close()
        sys.exit(1)
else:
    print("Binary already exists.")

# ── 2. Start server ──────────────────────────────────────────────────────────
print("\nStarting Ollama server...")
run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import subprocess, os\n"
    "env = dict(os.environ)\n"
    "env['OLLAMA_MODELS'] = '/tmp/ollama_models'\n"
    "env['HOME'] = '/tmp'\n"
    "env['PATH'] = '/tmp/bin:' + env.get('PATH', '')\n"
    "os.makedirs('/tmp/ollama_models', exist_ok=True)\n"
    "p = subprocess.Popen(['/tmp/bin/ollama', 'serve'],\n"
    "    env=env, stdout=open('/tmp/ollama.log','w'), stderr=subprocess.STDOUT)\n"
    "print('Ollama PID:', p.pid)\n"
    "\"",
    timeout=10
)
time.sleep(8)

# ── 3. Check server ──────────────────────────────────────────────────────────
out, _ = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import urllib.request, json\n"
    "try:\n"
    "    r = urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)\n"
    "    data = json.loads(r.read())\n"
    "    models = [m['name'] for m in data.get('models', [])]\n"
    "    print('UP models:', models)\n"
    "except Exception as e: print('DOWN:', e)\n"
    "\""
)
print("Server:", out)

if "DOWN" in out or not out:
    print("Server failed to start. Check /tmp/ollama.log:")
    out2, _ = run(f"kubectl exec {POD} -- tail -20 /tmp/ollama.log 2>&1")
    print(out2)
    client.close()
    sys.exit(1)

# ── 4. Pull model if needed ──────────────────────────────────────────────────
if "qwen" in out.lower():
    print("\nModel already available — ready!")
else:
    print("\nStarting model pull (~9GB, ~12 min)...")
    run(
        "kubectl exec " + POD + " -- python3 -c \""
        "import subprocess, os\n"
        "env = dict(os.environ)\n"
        "env['OLLAMA_MODELS'] = '/tmp/ollama_models'\n"
        "env['HOME'] = '/tmp'\n"
        "env['PATH'] = '/tmp/bin:' + env.get('PATH', '')\n"
        "p = subprocess.Popen(['/tmp/bin/ollama', 'pull', 'qwen2.5:14b-instruct-q4_K_M'],\n"
        "    env=env, stdout=open('/tmp/pull.log','w'), stderr=subprocess.STDOUT)\n"
        "print('Pull PID:', p.pid)\n"
        "\"",
        timeout=10
    )
    print("Monitoring (ctrl+c to stop monitoring, pull continues in background)...")
    for i in range(80):
        time.sleep(15)
        out, _ = run(f"kubectl exec {POD} -- tail -1 /tmp/pull.log 2>&1")
        pct = clean(out)
        print(f"  [{(i+1)*15}s] {pct[:80]}")
        if "success" in pct.lower():
            print("  PULL COMPLETE!")
            break

client.close()
print("Done.")
