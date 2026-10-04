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

# Start Ollama
print("Starting Ollama server...")
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
time.sleep(6)

# Check
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
    print("\nModel already available — app is ready to use!")
    print("Open browser and test the chat.")
else:
    print("\nPulling model (~12 min)...")
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

    # Monitor for 2 minutes then report
    print("Monitoring pull progress...")
    for i in range(8):
        time.sleep(15)
        out, _ = run(f"kubectl exec {POD} -- tail -1 /tmp/pull.log 2>&1")
        pct = clean(out)
        print(f"  [{(i+1)*15}s] {pct[:70]}")
        if "success" in pct.lower():
            print("  DONE!")
            break

client.close()
