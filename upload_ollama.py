"""Upload ollama binary from Windows to pod via SFTP, then start server and pull model."""
import paramiko, time, sys, os
sys.stdout.reconfigure(encoding='utf-8')

HOST = "10.255.11.254"
USER = "uniwai11"
PWD = "GbypPRuuyds"
POD = "physics-tutor-74b5558965-gj6qm"
LOCAL_BIN = r"c:\Users\thoma\Desktop\AI and DL\Thesis_ai_and_dl\ollama-linux-amd64"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PWD, timeout=30)
sftp = client.open_sftp()

def run(cmd, timeout=60):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8','replace').strip(), stderr.read().decode('utf-8','replace').strip()

# 1. Upload binary to bastion
print(f"Uploading ollama binary ({os.path.getsize(LOCAL_BIN)//1024//1024}MB) to bastion...")
sftp.put(LOCAL_BIN, "/tmp/ollama_upload")
print("Upload to bastion done.")

# 2. Copy from bastion to pod
print("Copying to pod...")
out, err = run(
    f"kubectl cp /tmp/ollama_upload {POD}:/tmp/ollama_upload && "
    f"kubectl exec {POD} -- bash -c "
    f"'mkdir -p /tmp/bin && mv /tmp/ollama_upload /tmp/bin/ollama && chmod +x /tmp/bin/ollama && ls -lh /tmp/bin/ollama'",
    timeout=120
)
print(out or err)

sftp.close()

if "ollama" not in (out + err):
    print("ERROR: copy to pod failed")
    client.close()
    sys.exit(1)

# 3. Start Ollama server
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
    "print('PID:', p.pid)\n"
    "\"",
    timeout=10
)
time.sleep(8)

# 4. Check server
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
print("Ollama:", out)

if "DOWN" in out or not out:
    out2, _ = run(f"kubectl exec {POD} -- tail -20 /tmp/ollama.log 2>&1")
    print("ollama.log:", out2)
    client.close()
    sys.exit(1)

# 5. Pull qwen2.5:3b
if "qwen" not in out.lower():
    print("\nPulling qwen2.5:3b (~2GB, ~3 min)...")
    run(
        "kubectl exec " + POD + " -- python3 -c \""
        "import subprocess, os\n"
        "env = dict(os.environ)\n"
        "env['OLLAMA_MODELS'] = '/tmp/ollama_models'\n"
        "env['HOME'] = '/tmp'\n"
        "env['PATH'] = '/tmp/bin:' + env.get('PATH', '')\n"
        "p = subprocess.Popen(['/tmp/bin/ollama', 'pull', 'qwen2.5:3b'],\n"
        "    env=env, stdout=open('/tmp/pull.log','w'), stderr=subprocess.STDOUT)\n"
        "print('Pull PID:', p.pid)\n"
        "\"",
        timeout=10
    )
    import re
    def clean(s): return re.sub(r'\x1b\[[0-9;]*[mGKlh]|\[K|\[A|\[1G|\[\?[0-9]+[lh]', '', s)
    for i in range(40):
        time.sleep(15)
        out, _ = run(f"kubectl exec {POD} -- tail -1 /tmp/pull.log 2>&1")
        pct = clean(out)
        print(f"  [{(i+1)*15}s] {pct[:80]}")
        if "success" in pct.lower():
            print("  DONE! Model ready.")
            break
else:
    print("Model already available!")

print("\nDone. Open browser and test.")
client.close()
