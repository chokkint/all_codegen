import os
import sys
import json
import argparse

DEBUG_ON = False

def debug(msg, *args):
    if DEBUG_ON:
        print("[DEBUG]", msg, *args)

class ObjectCollector:
    def __init__(self):
        self.objs = []
        self.all_types = set()
        self.all_fields = set()
    def record(self, typ, name, path, fields):
        self.objs.append({
            "type": typ, "name": name, "path": path, "fields": sorted(list(fields))
        })
        self.all_types.add(typ)
        self.all_fields.update(fields)
    def print_summary(self, prefix=""):
        print(f"\n==== AMIS对象统计 {prefix} ====")
        for o in self.objs:
            print(f"  [type:{o['type']:<10}] name:{o['name']:<15} path:{o['path']}")
            print(f"     字段: {o['fields']}")
        print(f"全部对象类型: {sorted(self.all_types)}")
        print(f"全部字段: {sorted(self.all_fields)}")
        print("=====================\n")

class StatCollector:
    def __init__(self):
        self.table_count = 0
        self.tables = []
        self.global_fields = set()
        self.global_attrs = set()
    def record_table(self, name, t, fields, apis):
        self.table_count += 1
        field_list = sorted(list(fields))
        api_list = [f"{a['op']}:{a['method']} {a['url']}" for a in apis]
        self.tables.append({
            'name': name, 'type': t, 'field_count': len(fields),
            'api_count': len(apis), 'field_list': field_list, 'api_list': api_list
        })
        self.global_fields.update(field_list)
    def record_attrs(self, d):
        if isinstance(d, dict):
            self.global_attrs.update(d.keys())
    def print_summary(self, prefix="", show_attrs=False):
        print(f"\n==== 统计汇总 {prefix} ====")
        print("命中表格区块数量:", self.table_count)
        for t in self.tables:
            print(f"  表名: {t['name']}  type: {t['type']}  字段数:{t['field_count']}  API数:{t['api_count']}")
            print(f"    字段: {t['field_list']}")
            print(f"    APIs: {t['api_list']}")
        if show_attrs:
            print("全局属性（所有dict key）:", sorted(self.global_attrs))
        print("全局字段（所有提取字段）:", sorted(self.global_fields))
        print("====================\n")

def upper_camel(s):
    parts = s.replace('-', '_').replace('.', '_').split('_')
    return ''.join([w[:1].upper() + w[1:] for w in parts if w])

def collect_all_fields(node, fields=None):
    if fields is None: fields = set()
    if isinstance(node, dict):
        if 'name' in node and isinstance(node['name'], str):
            fields.add(node['name'])
        for v in node.values():
            collect_all_fields(v, fields)
    elif isinstance(node, list):
        for item in node:
            collect_all_fields(item, fields)
    return fields

def amis_type_to_java_type(t):
    if t in ('input-date', 'input-datetime'):
        return 'java.util.Date'
    if t in ('input-number',): return 'Integer'
    return 'String'

def is_table_crud_type(type_str):
    if not isinstance(type_str, str): return False
    t = type_str.lower()
    return t.startswith('crud') or t.startswith('table')

def find_table_crud_blocks(data, stat: StatCollector, path="root"):
    result = []
    if isinstance(data, dict):
        t = data.get('type')
        stat.record_attrs(data)
        if is_table_crud_type(t): result.append(data)
        for v in data.values():
            result.extend(find_table_crud_blocks(v, stat))
    elif isinstance(data, list):
        for item in data:
            result.extend(find_table_crud_blocks(item, stat))
    return result

def extract_fields_from_list(lst):
    fields = []
    if not isinstance(lst, list): return fields
    for item in lst:
        if isinstance(item, dict) and item.get('name'):
            fields.append({
                'name': item['name'],
                'columnName': item.get('columnName', item['name']),
                'type': amis_type_to_java_type(item.get('type')),
                'label': item.get('label', item['name']),
                'description': item.get('label', item['name'])
            })
    return fields

def replace_base_url(url, base_url="http://your.base.url"):
    url = url.replace("${base_url}", base_url)
    url = url.replace("http://http://", "http://")
    url = url.replace("https://https://", "https://")
    return url

CRUD_BEHAVIOR = set([
    "insert", "add", "create",
    "edit", "update",
    "delete", "remove",
    "view", "query", "get"
])
def get_behavior_from_node(node):
    behaviors = set()
    for k in ("behavior", "feat"):
        v = node.get(k)
        if isinstance(v, list):
            behaviors.update(x.lower() for x in v if isinstance(x, str))
        elif isinstance(v, str):
            behaviors.add(v.lower())
    if isinstance(node.get("editorSetting"), dict):
        for k in ("behavior", "feat"):
            v = node["editorSetting"].get(k)
            if v:
                if isinstance(v, list):
                    behaviors.update(x.lower() for x in v if isinstance(x, str))
                elif isinstance(v, str):
                    behaviors.add(v.lower())
    if "actionType" in node and isinstance(node["actionType"], str):
        at = node["actionType"].lower()
        if at in {"add", "insert", "create", "edit", "update", "delete", "remove", "view", "ajax", "submit"}:
            behaviors.add(at)
    return behaviors

def is_crud_behavior(behaviors):
    for b in behaviors:
        if any(word in b for word in CRUD_BEHAVIOR):
            return True
    return False

def collect_crud_apis(node, apis=None, path="root"):
    if apis is None: apis = []
    if isinstance(node, dict):
        behaviors = get_behavior_from_node(node)
        if "api" in node and isinstance(node["api"], dict):
            method = node["api"].get("method", "").lower()
            url = node["api"].get("url", "")
            if is_crud_behavior(behaviors) or method in {"post", "put", "delete", "get"}:
                op = "query"
                if method == "post": op = "add"
                elif method == "put": op = "edit"
                elif method == "delete": op = "delete"
                elif method == "get": op = "view"
                apis.append({
                    "url": url,
                    "method": method,
                    "fields": [],
                    "op": op,
                    "path": path
                })
        if "onEvent" in node and isinstance(node["onEvent"], dict):
            for event, actions in node["onEvent"].items():
                acts = actions.get("actions") if isinstance(actions, dict) else actions
                if isinstance(acts, list):
                    for idx, a in enumerate(acts):
                        collect_crud_apis(a, apis, f"{path}.onEvent.{event}[{idx}]")
        for k in ("dialog", "drawer", "form"):
            if k in node and isinstance(node[k], dict):
                collect_crud_apis(node[k], apis, f"{path}.{k}")
        for k in ("actions", "body", "columns", "buttons", "items"):
            if k in node and isinstance(node[k], (list, dict)):
                collect_crud_apis(node[k], apis, f"{path}.{k}")
        for k, v in node.items():
            if k not in ("api", "onEvent", "dialog", "drawer", "form", "actions", "body", "columns", "buttons", "items"):
                collect_crud_apis(v, apis, f"{path}.{k}")
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            collect_crud_apis(item, apis, f"{path}[{idx}]")
    return apis

def scan_amis_objects(node, collector, path="root"):
    if isinstance(node, dict):
        typ = node.get('type')
        name = node.get('label', node.get('title', ''))
        fields = set()
        for k in ['columns', 'body', 'fields']:
            v = node.get(k)
            if v:
                fields.update(collect_all_fields(v))
        if typ in ('form', 'dialog', 'drawer'):
            if 'body' in node:
                fields.update(collect_all_fields(node['body']))
        if typ:
            collector.record(typ, name, path, fields)
        for k, v in node.items():
            scan_amis_objects(v, collector, f"{path}.{k}")
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            scan_amis_objects(item, collector, f"{path}[{idx}]")

def extract_main_table_name(amis_json, page_name):
    # 优先 crud/table 的 tableName，没有就用 page_name
    stat = StatCollector()
    blocks = find_table_crud_blocks(amis_json, stat)
    for crud in blocks:
        if 'tableName' in crud and crud['tableName']:
            return crud['tableName']
    return page_name

def amis_to_openapi(amis_json, page_name, amis_file, stat, obj_collector, base_url="http://your.base.url"):
    # 关键点：实体名全部以表名大驼峰为准
    if isinstance(amis_json, list):
        amis_json = {"body": amis_json}
    scan_amis_objects(amis_json, obj_collector)
    blocks = find_table_crud_blocks(amis_json, stat)
    blocks = [x for x in blocks if isinstance(x, dict)]
    if not blocks:
        raise ValueError("未发现 type 以 crud/table 开头的对象")
    openapis = []
    for idx, crud in enumerate(blocks):
        real_table_name = crud.get('tableName', page_name)
        entity_name = upper_camel(real_table_name)  # 全部以表名大驼峰为主
        fields_objs = []
        if 'columns' in crud:
            fields_objs.extend(extract_fields_from_list(crud['columns']))
        if not fields_objs:
            all_fields = collect_all_fields(crud)
            fields_objs = [{'name': f, 'columnName': f, 'type': 'String', 'label': f} for f in all_fields]
        apis = collect_crud_apis(crud)
        unique = {}
        for a in apis:
            k = (a['url'], a['method'])
            if k not in unique:
                unique[k] = a
        apis = list(unique.values())
        stat.record_table(real_table_name, crud.get('type'), [f['name'] for f in fields_objs], apis)
        paths = {}
        for api in apis:
            url = replace_base_url(api['url'], base_url)
            method = api['method']
            path_fields = fields_objs
            if url not in paths:
                paths[url] = {}
            if method == 'get':
                summary = f"查询{entity_name}"
            elif method == 'post':
                summary = f"新增{entity_name}"
            elif method == 'put':
                summary = f"编辑{entity_name}"
            elif method == 'delete':
                summary = f"删除{entity_name}"
            else:
                summary = f"{method.upper()} {entity_name}"
            if method == 'get':
                paths[url][method] = {
                    "tags": [entity_name],
                    "summary": summary,
                    "parameters": [
                        {
                            "name": f['name'],
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                            "description": f.get('label')
                        }
                        for f in path_fields
                    ],
                    "responses": {
                        "200": {
                            "description": f"{entity_name} 查询成功",
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
                    "summary": summary,
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        f['name']: {"type": "string", "description": f.get('label')}
                                        for f in path_fields
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
                    "summary": summary,
                    "parameters": [
                        {
                            "name": f['name'],
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": f.get('label')
                        }
                        for f in path_fields
                    ],
                    "responses": {"200": {"description": "删除成功"}}
                }
        schema = {
            "type": "object",
            "properties": {
                f['name']: {
                    "type": "string",
                    "javaType": f.get('type', 'String'),
                    "description": f.get('label', f['name']),
                    "columnName": f.get('columnName')
                } for f in fields_objs
            }
        }
        openapis.append({
            "openapi": "3.0.0",
            "info": {"title": entity_name, "tableName": real_table_name, "version": "1.0.0"},
            "paths": paths,
            "components": {
                "schemas": {
                    entity_name: schema
                }
            }
        })
    return openapis[0] if len(openapis) == 1 else openapis

def print_conversion_summary(conversion_list, amis_dir, system_name, field_max=4, api_max=2):
    print("\n======= 本次转换环境信息 =======")
    print(f"系统名：{system_name}")
    print(f"AMIS目录：{amis_dir}")
    print("==============================")
    print("\n========= 本次转换文件清单 =========")
    for idx, item in enumerate(conversion_list, 1):
        print(f"[{idx}] {item['file']}  ({item['table_name']}, {item['type']}, 字段: {item['field_count']}, API: {item['api_count']})")
        field_list = item['fields']
        if isinstance(field_list, str):
            field_list = [s.strip() for s in field_list.split(',') if s.strip()]
        if len(field_list) > field_max:
            field_short = ', '.join(field_list[:field_max]) + ', ...'
        else:
            field_short = ', '.join(field_list)
        print(f"    字段: {field_short}")
        apis = item['apis']
        if isinstance(apis, str):
            apis = [s.strip() for s in apis.split(',') if s.strip()]
        if len(apis) > api_max:
            api_short = '\n           '.join(apis[:api_max]) + "\n           ..."
        else:
            api_short = '\n           '.join(apis)
        print(f"    APIs: {api_short}\n")
    print("=" * 40)

def main():
    parser = argparse.ArgumentParser(description="AMIS JSON 批量转 OpenAPI JSON，支持多系统多页面结构")
    parser.add_argument('--system-name', default='test', help='系统名，默认为 test')
    parser.add_argument('--amis-dir', default=None, help='amis 源目录，未指定则为 docs/amis_json/<system_name>')
    parser.add_argument('--out-dir', default=None, help='输出目录，未指定则为 docs/openapi_json/<system_name>')
    parser.add_argument('--debug', action='store_true', help='开启调试日志')
    parser.add_argument('--show-attrs', action='store_true', help='输出全局属性')
    args = parser.parse_args()

    global DEBUG_ON
    DEBUG_ON = args.debug
    show_attrs = args.show_attrs

    system_name = args.system_name or 'test'
    amis_dir = args.amis_dir or os.path.join('.', 'docs', 'amis_json', system_name)
    out_dir = args.out_dir or os.path.join('.', 'docs', 'openapi_json', system_name)
    amis_dir = os.path.abspath(amis_dir)
    out_dir = os.path.abspath(out_dir)

    if not os.path.exists(amis_dir) or not os.path.isdir(amis_dir):
        print(f"[FATAL] amis-dir 不存在或不是目录: {amis_dir}")
        sys.exit(1)
    if not os.path.exists(out_dir):
        try:
            os.makedirs(out_dir)
            print(f"[INFO] 自动创建输出目录: {out_dir}")
        except Exception as e:
            print(f"[FATAL] 无法创建输出目录: {out_dir} - {e}")
            sys.exit(1)

    conversion_list = []

    for entry in os.listdir(amis_dir):
        path = os.path.join(amis_dir, entry)
        if os.path.isdir(path):
            for fname in os.listdir(path):
                if not fname.endswith('.json'):
                    continue
                amis_file = os.path.join(path, fname)
                try:
                    print(f"\n========== 处理文件: {amis_file} ==========")
                    with open(amis_file, encoding='utf-8') as f:
                        amis_json = json.load(f)
                    page_name = os.path.splitext(fname)[0]
                    table_name = extract_main_table_name(amis_json, page_name)
                    entity_name = upper_camel(table_name)
                    stat = StatCollector()
                    obj_collector = ObjectCollector()
                    scan_amis_objects(amis_json, obj_collector)
                    obj_collector.print_summary(f"[{amis_file}]")
                    openapi = amis_to_openapi(amis_json, page_name, amis_file, stat, obj_collector)
                    out_sys_path = os.path.join(out_dir, entry)
                    os.makedirs(out_sys_path, exist_ok=True)
                    out_file = os.path.join(out_sys_path, fname)
                    with open(out_file, 'w', encoding='utf-8') as fw:
                        json.dump(openapi, fw, ensure_ascii=False, indent=2)
                    print(f"[OK] 生成: {out_file}")
                    stat.print_summary(f"[{amis_file}]", show_attrs=show_attrs)
                    for t in stat.tables:
                        conversion_list.append({
                            'file': os.path.basename(amis_file),
                            'table_name': t['name'],
                            'type': t['type'],
                            'field_count': t['field_count'],
                            'api_count': t['api_count'],
                            'fields': ",".join(t['field_list']),
                            'apis': ",".join(t['api_list'])
                        })
                except Exception as e:
                    print(f"[ERROR] 文件 {amis_file} 处理失败: {e}")
        elif entry.endswith('.json'):
            amis_file = path
            try:
                print(f"\n========== 处理文件: {amis_file} ==========")
                with open(amis_file, encoding='utf-8') as f:
                    amis_json = json.load(f)
                page_name = os.path.splitext(entry)[0]
                table_name = extract_main_table_name(amis_json, page_name)
                entity_name = upper_camel(table_name)
                stat = StatCollector()
                obj_collector = ObjectCollector()
                scan_amis_objects(amis_json, obj_collector)
                obj_collector.print_summary(f"[{amis_file}]")
                openapi = amis_to_openapi(amis_json, page_name, amis_file, stat, obj_collector)
                out_file = os.path.join(out_dir, entry)
                with open(out_file, 'w', encoding='utf-8') as fw:
                    json.dump(openapi, fw, ensure_ascii=False, indent=2)
                print(f"[OK] 生成: {out_file}")
                stat.print_summary(f"[{amis_file}]", show_attrs=show_attrs)
                for t in stat.tables:
                    conversion_list.append({
                        'file': os.path.basename(amis_file),
                        'table_name': t['name'],
                        'type': t['type'],
                        'field_count': t['field_count'],
                        'api_count': t['api_count'],
                        'fields': ",".join(t['field_list']),
                        'apis': ",".join(t['api_list'])
                    })
            except Exception as e:
                print(f"[ERROR] 文件 {amis_file} 处理失败: {e}")

    print_conversion_summary(conversion_list, amis_dir, system_name)

if __name__ == '__main__':
    main()
