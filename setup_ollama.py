import paramiko, time, sys
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
    return stdout.read().decode('utf-8','replace').strip(), stderr.read().decode('utf-8','replace').strip()

# 1. Download ollama binary
print("=== Downloading Ollama binary ===")
out, err = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import urllib.request, os, stat\n"
    "os.makedirs('/tmp/bin', exist_ok=True)\n"
    "url = 'https://github.com/ollama/ollama/releases/download/v0.6.5/ollama-linux-amd64'\n"
    "print('Downloading...')\n"
    "urllib.request.urlretrieve(url, '/tmp/bin/ollama')\n"
    "os.chmod('/tmp/bin/ollama', 0o755)\n"
    "print('Done:', os.path.getsize('/tmp/bin/ollama'))\n"
    "\"",
    timeout=120
)
print(out or err[:300])

# 2. Start Ollama server
print("\n=== Starting Ollama server ===")
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
    "print('PID:', p.pid)\n"
    "\"",
    timeout=10
)
print("Waiting 8s for server startup...")
time.sleep(8)

# 3. Check server
out, _ = run(
    "kubectl exec " + POD + " -- python3 -c \""
    "import urllib.request, json\n"
    "try:\n"
    "    r = urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)\n"
    "    data = json.loads(r.read())\n"
    "    models = [m['name'] for m in data.get('models', [])]\n"
    "    print('UP, models:', models)\n"
    "except Exception as e: print('DOWN:', e)\n"
    "\""
)
print("Ollama:", out)

if "qwen" in out.lower():
    print("\nModel ready — app is good to go!")
else:
    print("\n=== Pulling model (~12 min) ===")
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
    print("Pull started. Monitoring for 15 min...")
    for i in range(60):
        time.sleep(15)
        out, _ = run("kubectl exec " + POD + " -- tail -1 /tmp/pull.log 2>&1")
        import re
        pct = re.sub(r'\x1b\[[0-9;]*[mGKlh]|\[K|\[A|\[1G|\[\?[0-9]+[lh]', '', out)
        print(f"  [{(i+1)*15}s] {pct[:80]}")
        if "success" in pct.lower():
            print("  DONE!")
            break

client.close()
print("\nDone.")
