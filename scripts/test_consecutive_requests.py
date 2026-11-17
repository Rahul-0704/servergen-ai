import urllib.request
import json
import time

def main():
    print("Testing consecutive requests...")
    login_data = json.dumps({'username': 'operator', 'password': 'Operator1!'}).encode('utf-8')
    req = urllib.request.Request('http://127.0.0.1:8000/api/v1/auth/login', data=login_data, headers={'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(req)
    token = json.loads(resp.read().decode('utf-8'))['access_token']

    for i in range(1, 4):
        t0 = time.time()
        body = json.dumps({
            'input': f'Query #{i}: What permissions are assigned to the IT Operator role according to RBAC docs?',
            'data_sensitivity': 'internal',
            'model': 'llama3.2:3b'
        }).encode('utf-8')
        req_ai = urllib.request.Request('http://127.0.0.1:8000/api/v1/ai/execute', data=body, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'})
        try:
            resp_ai = urllib.request.urlopen(req_ai)
            data = json.loads(resp_ai.read().decode('utf-8'))
            elapsed = round(time.time() - t0, 2)
            print(f"Attempt #{i}: HTTP {resp_ai.status} | success={data.get('success')} | decision={data.get('policy_decision')} | time={elapsed}s | content_len={len(data.get('content', ''))}")
        except urllib.error.HTTPError as e:
            print(f"Attempt #{i}: HTTP ERROR {e.code} - {e.read().decode('utf-8')}")
        except Exception as e:
            print(f"Attempt #{i}: EXCEPTION - {e}")

if __name__ == '__main__':
    main()
