import os
import json
import argparse

def camel_case(s):
    parts = s.replace('-', '_').replace('.', '_').split('_')
    return ''.join([w[:1].upper() + w[1:].lower() for w in parts if w])

def amis_type_to_java_type(t):
    if t in ('input-date', 'input-datetime'):
        return 'java.util.Date'
    if t in ('input-number',):
        return 'Integer'
    return 'String'

def extract_fields_from_list(lst):
    fields = []
    for item in lst:
        if isinstance(item, dict) and item.get('name'):
            fields.append({
                'name': item['name'],
                'type': amis_type_to_java_type(item.get('type')),
                'label': item.get('label', item['name']),
                'description': item.get('label', item['name'])
            })
    return fields

def extract_crud_apis(crud):
    apis = []
    # 查询API
    if 'api' in crud:
        api = crud['api']
        url = api['url']
        method = api.get('method', 'get').lower()
        filter_fields = []
        if crud.get('filter', {}).get('body'):
            filter_fields = extract_fields_from_list(crud['filter']['body'])
        elif 'filterEnabledList' in crud:
            filter_fields = [{'name': f['value'], 'type': 'String', 'label': f['label']} for f in crud['filterEnabledList']]
        apis.append({'url': url, 'method': method, 'fields': filter_fields, 'op': 'query'})
    # 新增API
    for tb in crud.get('headerToolbar', []):
        if isinstance(tb, dict) and tb.get('actionType') == 'dialog' and tb.get('dialog', {}).get('body', {}).get('api', {}).get('method', '').lower() == 'post':
            add_api = tb['dialog']['body']['api']
            url = add_api['url']
            method = add_api.get('method', 'post').lower()
            form_body = tb['dialog']['body']['body']
            add_fields = extract_fields_from_list(form_body)
            apis.append({'url': url, 'method': method, 'fields': add_fields, 'op': 'add'})
    # 编辑API
    for col in crud.get('columns', []):
        if col.get('type') == 'operation':
            for btn in col.get('buttons', []):
                if btn.get('actionType') == 'dialog' and btn.get('dialog', {}).get('body', {}).get('api', {}).get('method', '').lower() == 'put':
                    edit_api = btn['dialog']['body']['api']
                    url = edit_api['url']
                    method = edit_api.get('method', 'put').lower()
                    form_body = btn['dialog']['body']['body']
                    edit_fields = extract_fields_from_list(form_body)
                    apis.append({'url': url, 'method': method, 'fields': edit_fields, 'op': 'edit'})
                # 删除API
                if btn.get('actionType') == 'ajax' and btn.get('api', {}).get('method', '').lower() == 'delete':
                    del_api = btn['api']
                    url = del_api['url']
                    method = del_api.get('method', 'delete').lower()
                    apis.append({'url': url, 'method': method, 'fields': [{'name': 'ODS_ID', 'type': 'String', 'label': '主键'}], 'op': 'delete'})
    return apis

# 新增：递归查找所有 crud 对象
def find_crud(data):
    result = []
    if isinstance(data, dict):
        if data.get('type') == 'crud':
            result.append(data)
        for v in data.values():
            result.extend(find_crud(v))
    elif isinstance(data, list):
        for item in data:
            result.extend(find_crud(item))
    return result

def amis_to_openapi(amis_json, entity_name, table_name):
    cruds = find_crud(amis_json)
    if not cruds:
        raise ValueError("未发现crud")
    # 支持多个 crud，逐个输出
    openapis = []
    for idx, crud in enumerate(cruds):
        apis = extract_crud_apis(crud)
        # 汇总所有字段（去重）
        all_fields = {}
        for api in apis:
            for f in api['fields']:
                all_fields[f['name']] = f
        # openapi paths
        paths = {}
        for api in apis:
            url = api['url']
            method = api['method']
            fields = api['fields']
            if url not in paths:
                paths[url] = {}
            if method == 'get':
                paths[url][method] = {
                    "tags": [entity_name],
                    "summary": "查询" + entity_name,
                    "parameters": [
                        {
                            "name": f['name'],
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                            "description": f.get('label')
                        }
                        for f in fields
                    ],
                    "responses": {
                        "200": {
                            "description": "查询成功",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": f"#/components/schemas/{entity_name}"}
                                }
                            }
                        }
                    }
                }
            elif method in ('post', 'put'):
                paths[url][method] = {
                    "tags": [entity_name],
                    "summary": ("新增" if api['op'] == 'add' else '编辑') + entity_name,
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        f['name']: {"type": "string", "description": f.get('label')}
                                        for f in fields
                                    }
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "操作成功"}}
                }
            elif method == 'delete':
                paths[url][method] = {
                    "tags": [entity_name],
                    "summary": "删除" + entity_name,
                    "parameters": [
                        {
                            "name": f['name'],
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": f.get('label')
                        }
                        for f in fields
                    ],
                    "responses": {"200": {"description": "删除成功"}}
                }
        # 统一 schema
        schema = {
            "type": "object",
            "properties": {
                f['name']: {
                    "type": "string",
                    "javaType": f['type'],
                    "description": f['label']
                } for f in all_fields.values()
            }
        }
        openapis.append({
            "openapi": "3.0.0",
            "info": {"title": entity_name, "tableName": table_name, "version": "1.0.0"},
            "paths": paths,
            "components": {
                "schemas": {
                    entity_name: schema
                }
            }
        })
    # 只返回第一个 crud，或可以自行保存全部
    return openapis[0] if len(openapis) == 1 else openapis

def main():
    parser = argparse.ArgumentParser(description="AMIS JSON 批量转 OpenAPI JSON")
    parser.add_argument('--amis-dir', default='./docs/amis_json', help='amis 源目录')
    parser.add_argument('--out-dir', default='./docs/openapi_json', help='输出目录')
    args = parser.parse_args()

    amis_dir = args.amis_dir
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)

    for entry in os.listdir(amis_dir):
        path = os.path.join(amis_dir, entry)
        if os.path.isdir(path):
            # 多系统目录结构
            for fname in os.listdir(path):
                if not fname.endswith('.json'):
                    continue
                amis_file = os.path.join(path, fname)
                with open(amis_file, encoding='utf-8') as f:
                    amis_json = json.load(f)
                page_name = os.path.splitext(fname)[0]
                entity_name = camel_case(page_name)
                table_name = page_name.upper()
                try:
                    openapi = amis_to_openapi(amis_json, entity_name, table_name)
                    out_sys_path = os.path.join(out_dir, entry)
                    os.makedirs(out_sys_path, exist_ok=True)
                    out_file = os.path.join(out_sys_path, fname)
                    with open(out_file, 'w', encoding='utf-8') as fw:
                        json.dump(openapi, fw, ensure_ascii=False, indent=2)
                    print(f"生成: {out_file}")
                except Exception as e:
                    print(f"文件 {amis_file} 处理失败: {e}")
        elif entry.endswith('.json'):
            # 直接 amis_json/page1.json 结构
            amis_file = path
            with open(amis_file, encoding='utf-8') as f:
                amis_json = json.load(f)
            page_name = os.path.splitext(entry)[0]
            entity_name = camel_case(page_name)
            table_name = page_name.upper()
            try:
                openapi = amis_to_openapi(amis_json, entity_name, table_name)
                out_file = os.path.join(out_dir, entry)
                with open(out_file, 'w', encoding='utf-8') as fw:
                    json.dump(openapi, fw, ensure_ascii=False, indent=2)
                print(f"生成: {out_file}")
            except Exception as e:
                print(f"文件 {amis_file} 处理失败: {e}")

if __name__ == '__main__':
    main()
