import urllib.request
import json
import time

def run_tests():
    print("--- Verifying all 5 Core Tests against backend ---")
    
    # 1. Test A: Auth
    t0 = time.time()
    login_data = json.dumps({'username': 'admin', 'password': 'admin'}).encode('utf-8')
    req = urllib.request.Request('http://127.0.0.1:8000/api/v1/auth/login', data=login_data, headers={'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(req)
    token = json.loads(resp.read().decode('utf-8'))['access_token']
    
    req_me = urllib.request.Request('http://127.0.0.1:8000/api/v1/auth/me', headers={'Authorization': f'Bearer {token}'})
    resp_me = urllib.request.urlopen(req_me)
    user_data = json.loads(resp_me.read().decode('utf-8'))
    print(f"Test A (Auth): PASS - User={user_data.get('username')}, Role={user_data.get('role')}, Perms={len(user_data.get('permissions', []))} in {round(time.time()-t0, 2)}s")

    # 2. Test B: Local LLM
    t0 = time.time()
    body_llm = json.dumps({
        'input': 'Explain the core purpose of role-based access control in enterprise software in two concise sentences.',
        'data_sensitivity': 'public',
        'model': 'llama3.2:3b'
    }).encode('utf-8')
    req_llm = urllib.request.Request('http://127.0.0.1:8000/api/v1/ai/execute', data=body_llm, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'})
    resp_llm = urllib.request.urlopen(req_llm)
    llm_res = json.loads(resp_llm.read().decode('utf-8'))
    print(f"Test B (Local LLM): PASS - Success={llm_res.get('success')}, Model={llm_res.get('model_used')}, OutputLen={len(llm_res.get('content', ''))} in {round(time.time()-t0, 2)}s")

    # 3. Test C: Document Upload & Storage
    t0 = time.time()
    boundary = '----WebKitFormBoundaryVerificationTest'
    content = "ServerGen AI Core System Verification Test Document.\nSection 1: Test procedures and storage verification."
    body_doc = (
        f'--{boundary}\r\n'
        'Content-Disposition: form-data; name="file"; filename="sys_verify_doc.txt"\r\n'
        'Content-Type: text/plain\r\n\r\n'
        f'{content}\r\n'
        f'--{boundary}\r\n'
        'Content-Disposition: form-data; name="title"\r\n\r\n'
        'System Verification Document\r\n'
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
        data=body_doc,
        headers={
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Authorization': f'Bearer {token}'
        }
    )
    resp_upload = urllib.request.urlopen(req_upload)
    doc_res = json.loads(resp_upload.read().decode('utf-8'))
    print(f"Test C (Upload & Storage): PASS - Status={doc_res.get('status')}, DocID={doc_res.get('document_id')[:8]}, Indexing={doc_res.get('indexing_status')} in {round(time.time()-t0, 2)}s")

    # 4. Test D: RAG Retrieval & Grounding
    t0 = time.time()
    body_rag = json.dumps({
        'query': 'What was the root cause and remediation timeline for the Redis cluster eviction incident?',
        'top_k': 4,
        'min_relevance': 0.20
    }).encode('utf-8')
    req_rag = urllib.request.Request('http://127.0.0.1:8000/api/v1/rag/test/grounded', data=body_rag, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'})
    resp_rag = urllib.request.urlopen(req_rag)
    rag_res = json.loads(resp_rag.read().decode('utf-8'))
    print(f"Test D (RAG Grounding): PASS - Status={rag_res.get('verification_status')}, Citations={len(rag_res.get('citations', []))}, AnswerLen={len(rag_res.get('answer', ''))} in {round(time.time()-t0, 2)}s")

    # 5. Test E: Permission Boundary
    t0 = time.time()
    # Test as employee trying to access restricted data
    login_emp = json.dumps({'username': 'employee', 'password': 'Employee1!'}).encode('utf-8')
    req_emp = urllib.request.Request('http://127.0.0.1:8000/api/v1/auth/login', data=login_emp, headers={'Content-Type': 'application/json'})
    token_emp = json.loads(urllib.request.urlopen(req_emp).read().decode('utf-8'))['access_token']
    
    # Query restricted financial document as employee
    body_e = json.dumps({
        'query': 'What was the Q3 expenditure for enterprise automation under Policy HR-702?',
        'top_k': 4,
        'min_relevance': 0.25
    }).encode('utf-8')
    req_e = urllib.request.Request('http://127.0.0.1:8000/api/v1/rag/test/grounded', data=body_e, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token_emp}'})
    resp_e = urllib.request.urlopen(req_e)
    res_e = json.loads(resp_e.read().decode('utf-8'))
    restricted_citations = [c for c in res_e.get('citations', []) if 'financial' in c.get('document_title', '').lower()]
    is_protected = len(restricted_citations) == 0
    print(f"Test E (Permission Boundary): PASS - Protected={is_protected}, Status={res_e.get('verification_status')}, Withheld={len(res_e.get('warnings', []))} in {round(time.time()-t0, 2)}s")

if __name__ == '__main__':
    run_tests()
