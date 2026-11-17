import urllib.request
import json

def main():
    print("Testing consecutive document uploads...")
    login_data = json.dumps({'username': 'operator', 'password': 'Operator1!'}).encode('utf-8')
    req = urllib.request.Request('http://127.0.0.1:8000/api/v1/auth/login', data=login_data, headers={'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(req)
    token = json.loads(resp.read().decode('utf-8'))['access_token']

    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    for i in range(1, 3):
        content = f"ServerGen AI Enterprise Knowledge Document #{i}.\nSection 1: Procedures and guidelines for IT operations team #{i}."
        body = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="file"; filename="consec_doc_{i}.txt"\r\n'
            'Content-Type: text/plain\r\n\r\n'
            f'{content}\r\n'
            f'--{boundary}\r\n'
            'Content-Disposition: form-data; name="title"\r\n\r\n'
            f'Consecutive Test Doc {i}\r\n'
            f'--{boundary}\r\n'
            'Content-Disposition: form-data; name="category"\r\n\r\n'
            'operations\r\n'
            f'--{boundary}\r\n'
            'Content-Disposition: form-data; name="classification"\r\n\r\n'
            'internal\r\n'
            f'--{boundary}--\r\n'
        ).encode('utf-8')

        req_upload = urllib.request.Request(
            'http://127.0.0.1:8000/api/v1/rag/upload',
            data=body,
            headers={
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'Authorization': f'Bearer {token}'
            }
        )
        resp_upload = urllib.request.urlopen(req_upload)
        d = json.loads(resp_upload.read().decode('utf-8'))
        print(f"Upload #{i}: status={d.get('status')} | doc_id={d.get('document_id')} | indexing_status={d.get('indexing_status')}")

if __name__ == '__main__':
    main()
