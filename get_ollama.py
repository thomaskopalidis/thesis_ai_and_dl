"""Try downloading ollama binary from alternative sources inside the pod."""
import paramiko, time, sys
sys.stdout.reconfigure(encoding='utf-8')
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('10.255.11.254', username='uniwai11', password='GbypPRuuyds', timeout=30)
def run(cmd, timeout=60):
    s, o, e = client.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8','replace').strip(), e.read().decode('utf-8','replace').strip()
POD = "physics-tutor-74b5558965-gj6qm"

# Try the install script approach - it uses curl internally
# First test if github releases is accessible
out, err = run(
    f"kubectl exec {POD} -- python3 -c \""
    "import urllib.request\n"
    "url = 'https://objects.githubusercontent.com/github-production-release-asset-2e65be/465300185/0b8e5a03-08b8-4e1b-b9b6-5abb45db9c8c'\n"
    "try:\n"
    "    r = urllib.request.urlopen(url, timeout=5)\n"
    "    print('githubusercontent OK:', r.status)\n"
    "except Exception as e: print('FAIL:', str(e)[:80])\n"
    "\""
)
print("githubusercontent:", out or err[:100])

# Try pip install ollama-server or find another way
# Actually - use the install.sh which handles everything
out, err = run(
    f"kubectl exec {POD} -- bash -c 'curl -fsSL https://ollama.com/install.sh | OLLAMA_INSTALL_DIR=/tmp/bin sh 2>&1 | tail -5'",
    timeout=120
)
print("install.sh:", out or err[:300])

# Check result
out, err = run(f"kubectl exec {POD} -- ls -lh /tmp/bin/ollama 2>&1")
print("binary:", out or err)

client.close()
