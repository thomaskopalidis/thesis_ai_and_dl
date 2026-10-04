"""
Upload fix + download ollama via SSH jump (wget on the bastion, then scp to pod).
"""
import paramiko, time, sys
sys.stdout.reconfigure(encoding='utf-8')

HOST = "10.255.11.254"
USER = "uniwai11"
PWD = "GbypPRuuyds"
POD = "physics-tutor-74b5558965-gj6qm"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PWD, timeout=30)
sftp = client.open_sftp()

def run(cmd, timeout=60):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8','replace').strip()
    err = stderr.read().decode('utf-8','replace').strip()
    return out, err

# 1. Verify wav2lip fix already uploaded
out, _ = run(f"kubectl exec {POD} -- grep -c 'PYTHONPATH' /workspace/physics_tutor/core/wav2lip_lipsync.py 2>&1")
print("PYTHONPATH lines in wav2lip_lipsync.py:", out)

# 2. Check if wget works on bastion
print("\nChecking wget on bastion...")
out, err = run("which wget 2>&1")
print("wget:", out or err)

out, err = run("which curl 2>&1")
print("curl:", out or err)

# 3. Download ollama to bastion first, then copy to pod
print("\nDownloading ollama to bastion /tmp/ollama_bin ...")
out, err = run(
    "wget -q --show-progress -O /tmp/ollama_bin "
    "https://github.com/ollama/ollama/releases/download/v0.6.5/ollama-linux-amd64 2>&1 && "
    "chmod +x /tmp/ollama_bin && ls -lh /tmp/ollama_bin",
    timeout=300
)
print(out or err)

if "ollama_bin" not in (out+err) or "No such" in (out+err):
    # try curl
    print("wget failed, trying curl...")
    out, err = run(
        "curl -fsSL -o /tmp/ollama_bin "
        "https://github.com/ollama/ollama/releases/download/v0.6.5/ollama-linux-amd64 && "
        "chmod +x /tmp/ollama_bin && ls -lh /tmp/ollama_bin",
        timeout=300
    )
    print(out or err)

# 4. Copy from bastion to pod
print("\nCopying ollama to pod...")
out, err = run(
    f"kubectl cp /tmp/ollama_bin {POD}:/tmp/ollama_bin && "
    f"kubectl exec {POD} -- bash -c 'mkdir -p /tmp/bin && cp /tmp/ollama_bin /tmp/bin/ollama && chmod +x /tmp/bin/ollama && ls -lh /tmp/bin/ollama'",
    timeout=120
)
print(out or err)

if "ollama" not in (out+err):
    print("Copy to pod failed!")
    client.close()
    sys.exit(1)

# 5. Start Ollama server
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

# 6. Check server
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
    out2, _ = run(f"kubectl exec {POD} -- tail -10 /tmp/ollama.log 2>&1")
    print("ollama.log:", out2)
    client.close()
    sys.exit(1)

# 7. Pull qwen2.5:3b (~2GB, fast)
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
            print("  DONE!")
            break
else:
    print("Model already available!")

print("\nDone. Test in browser now.")
client.close()
