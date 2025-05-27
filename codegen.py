import os
import json
import argparse
import shutil
from zipfile import ZipFile
from jinja2 import Environment, FileSystemLoader

def upper_camel(s):
    return ''.join([w.capitalize() for w in s.replace('-', '_').replace('.', '_').split('_')])

def small_camel(s):
    parts = s.lower().split('_')
    return parts[0] + ''.join([w.capitalize() for w in parts[1:]])

def get_primary_key_field(fields):
    for f in fields:
        if f.get('primaryKey', False):
            return f
    # 常用主键名兜底
    for f in fields:
        if f['name'].lower() in ('id', 'pk', 'trade_id', 'user_id', 'ods_id'):
            return f
    # 回退第一个
    return fields[0] if fields else None

def get_primary_key_field(fields):
    # 优先找primaryKey，其次常用主键名
    for f in fields:
        if f.get('primaryKey', False):
            return f
    # 常见主键名
    for f in fields:
        if f['name'].lower() in ('id', 'pk', 'trade_id', 'user_id', 'ods_id'):
            return f
    # 回退第一个
    return fields[0] if fields else None

def package_from_path(system_name, page_name, base_package):
    # 去除任何为空的元素，防止多点
    segments = [base_package]
    if system_name:
        segments.append(system_name.lower())
    if page_name:
        segments.append(page_name.lower())
    return ".".join(segments)

def openapi_method_to_mapping(method):
    std_methods = {
        'get': 'GetMapping',
        'post': 'PostMapping',
        'put': 'PutMapping',
        'delete': 'DeleteMapping',
        'patch': 'PatchMapping',
        'options': 'RequestMapping',
        'head': 'RequestMapping'
    }
    m = method.lower()
    mapping = std_methods.get(m)
    if not mapping:
        print(f"[warn] 未知HTTP方法: {method}，默认使用@RequestMapping")
        mapping = 'RequestMapping'
    return mapping

def render_template(env, template_name, **kwargs):
    template = env.get_template(template_name)
    return template.render(**kwargs)

def get_fields_from_schema(schema):
    fields = []
    for fname, finfo in schema.get('properties', {}).items():
        fields.append({
            'name': fname,
            'type': finfo.get('javaType', 'String'),
            'label': finfo.get('description', fname),
            'java_name': small_camel(fname),
            'java_type': finfo.get('javaType', 'String'),
        })
    return fields or [{'name': 'id', 'type': 'Long', 'java_name': 'id', 'java_type': 'Long', 'label': '主键ID'}]

def extract_paths(openapi):
    paths = []
    for url, methods in openapi.get('paths', {}).items():
        for method, api in methods.items():
            paths.append({
                'url': url,
                'method': method,
                'mapping': openapi_method_to_mapping(method),
                'parameters': api.get('parameters', []),
                'requestBody': api.get('requestBody', {}),
                'summary': api.get('summary', ''),
                'responses': api.get('responses', {}),
                'operationId': api.get('operationId', f"{method}_{url.replace('/', '_')}")
            })
    return paths

def generate_entity_repository_model(env, backend_dir, java_root, model_class_name, fields, package_prefix, table_name):
    pk_field = get_primary_key_field(fields)
    pk_type = pk_field['java_type'] if pk_field else 'Long'  # 默认 Long
    print('pk_type = '+pk_type)
    layers = {
        'entity.java.j2': f'entity/{model_class_name}Entity.java',
        'repository.java.j2': f'repository/{model_class_name}Repository.java',
        'model.java.j2': f'model/{model_class_name}Model.java',
    }
    variables = {
        'package_name': package_prefix,
        'model_class_name': f"{model_class_name}Model",
        'entity_class_name': f"{model_class_name}Entity",
        'repository_class_name': f"{model_class_name}Repository",
        'table_name': table_name,  # <--- 新增
        'fields': [
            {
                'name': f['name'], # <--- 数据库字段名（全大写，下划线）
                'db_column': f['name'],        # 明确传 db_column
                'type': f['java_type'],
                'java_name': f['java_name'],
                'java_type': f['java_type'],
                'label': f.get('label', f['java_name']),
                # 'pk_type': pk_type,  # <--- 一定要有这一行
                'primary_key': f.get('primaryKey', False)
            }
            for f in fields
        ],
        'pk_type': pk_type
    }
    print("[DEBUG repository]", variables)
    for key, sub_path in layers.items():
        tgt_dir = os.path.join(backend_dir, java_root, os.path.dirname(sub_path))
        os.makedirs(tgt_dir, exist_ok=True)
        code = render_template(env, key, **variables)
        with open(os.path.join(tgt_dir, os.path.basename(sub_path)), 'w', encoding='utf-8') as fw:
            fw.write(code)

def generate_for_page(env, backend_dir, java_root, system_name, page_name, openapi, base_package, app_class_name, artifact_id):
    table_name = openapi.get('info', {}).get('tableName', page_name)
    model_class_name = upper_camel(table_name)
    page_class_name = upper_camel(page_name)
    page_package_name = package_from_path(system_name, page_name, base_package)
    schemas = openapi.get('components', {}).get('schemas', {})
    page_schema_key = upper_camel(page_name)
    schema = schemas.get(page_schema_key, {}) or schemas.get(model_class_name, {})
    if not schema:
        print(f"[error] 未找到schema定义，schemas keys: {list(schemas.keys())}")
    fields = get_fields_from_schema(schema)

    # 提取 GET 查询参数
    query_params = []
    for path in extract_paths(openapi):
        if path['method'].lower() == 'get':
            for p in path.get('parameters', []):
                query_params.append({
                    'java_type': p.get('schema', {}).get('type', 'String').capitalize(),
                    'java_name': small_camel(p['name']),
                    'name': p['name'],
                    'desc': p.get('description', p['name'])
                })
    query_params_str = ', '.join([f"{p['java_type']} {p['java_name']}" for p in query_params])
    query_param_names = [p['java_name'] for p in query_params]
    variables = {
        'package_name': page_package_name,
        'page_class_name': page_class_name,
        'model_class_name': model_class_name,
        'entity_class_name': f"{model_class_name}Entity",
        'fields': fields,
        'controller_class_name': f"{page_class_name}Controller",
        'service_class_name': f"{page_class_name}Service",
        'service_impl_class_name': f"{page_class_name}ServiceImpl",
        'service_instance_name': small_camel(page_class_name) + "Service",
        'repository_class_name': f"{model_class_name}Repository",
        'dto_class_name': f"{model_class_name}DTO",
        'apis': extract_paths(openapi),
        'app_class_name': app_class_name,
        'artifact_id': artifact_id,
        'page_name': page_name,
        'query_params': query_params,
        'query_params_str': query_params_str,
        'query_param_names': query_param_names
    }
        # 提取 pk_field 查询参数
    pk_field = get_primary_key_field(fields)
    variables['pk_field_name'] = pk_field['name']
    variables['pk_field_java_name'] = pk_field['java_name']
    variables['pk_field_java_type'] = pk_field['java_type']
    # Controller
    page_dir = os.path.join(backend_dir, java_root, page_name)
    controller_dir = os.path.join(page_dir, 'controller')
    os.makedirs(controller_dir, exist_ok=True)
    ctrl_code = render_template(env, 'controller.java.j2', **variables)
    with open(os.path.join(controller_dir, f"{page_class_name}Controller.java"), 'w', encoding='utf-8') as fw:
        fw.write(ctrl_code)
    # Service
    service_dir = os.path.join(page_dir, 'service')
    os.makedirs(service_dir, exist_ok=True)
    service_code = render_template(env, 'service.java.j2', **variables)
    with open(os.path.join(service_dir, f"{page_class_name}Service.java"), 'w', encoding='utf-8') as fw:
        fw.write(service_code)
    # ServiceImpl
    impl_dir = os.path.join(service_dir, 'impl')
    os.makedirs(impl_dir, exist_ok=True)
    service_impl_code = render_template(env, 'serviceImpl.java.j2', **variables)
    with open(os.path.join(impl_dir, f"{page_class_name}ServiceImpl.java"), 'w', encoding='utf-8') as fw:
        fw.write(service_impl_code)
    # DTO
    # print(f"[debug] model_class_name: {model_class_name}")
    # print(f"[debug] schema: {schema}")
    # print(f"[debug] fields: {fields}")
    dto_dir = os.path.join(page_dir, 'dto')
    os.makedirs(dto_dir, exist_ok=True)
    dto_code = render_template(env, 'dto.java.j2', **variables)
    with open(os.path.join(dto_dir, f"{model_class_name}DTO.java"), 'w', encoding='utf-8') as fw:
        fw.write(dto_code)

def check_consistency(output_dir, system_name, expected_structure):
    """
    简单一致性校验：检查生成的目录、关键文件是否完整、符合标准。
    可进一步扩展内容检查。
    """
    backend_dir = os.path.join(output_dir, f"{system_name}-backend")
    for path in expected_structure:
        full_path = os.path.join(backend_dir, path)
        if not os.path.exists(full_path):
            print(f"[ERROR] 缺少关键输出：{full_path}")
            return False
    print("[一致性校验] 结构完整，通过。")
    return True

def make_zip_dir(src_dir, zip_path):
    with ZipFile(zip_path, 'w') as zipf:
        for folder_name, subfolders, filenames in os.walk(src_dir):
            for filename in filenames:
                file_path = os.path.join(folder_name, filename)
                arcname = os.path.relpath(file_path, src_dir)
                zipf.write(file_path, arcname)
    print(f"✅ 已生成工程 ZIP 包：{zip_path}")

def main():
    parser = argparse.ArgumentParser(description="OpenAPI 自动生成 Java 微服务工程代码")
    parser.add_argument('--package-prefix', default='com.hg', help='Java package 前缀')
    parser.add_argument('--openapi-dir', default='./docs/openapi_json', help='OpenAPI JSON 根目录')
    parser.add_argument('--output-dir', default='./output', help='输出目录')
    parser.add_argument('--templates-dir', default='./templates', help='模板目录')
    # parser.add_argument('--with-common', action='store_true', help='（仅用于全量交付）同时输出 common-backend 源码')
    parser.add_argument('--zip', action='store_true', help='输出主工程 zip 包')
    args = parser.parse_args()
    base_package = args.package_prefix  # 只用 com.hg，绝不加 system_name！

    env = Environment(loader=FileSystemLoader(args.templates_dir), trim_blocks=True, lstrip_blocks=True)

    # 注册自定义过滤器
    def upper_first(s):
        return s[0].upper() + s[1:] if s else s
    env.filters['upper_first'] = upper_first

    for system_name in os.listdir(args.openapi_dir):
        sys_dir = os.path.join(args.openapi_dir, system_name)
        if not os.path.isdir(sys_dir):
            continue
        artifact_id = f"{system_name}-backend"
        app_class_name = upper_camel(system_name) + "ApiApplication"
        backend_dir = os.path.join(args.output_dir, artifact_id)
        java_root = f'src/main/java/{args.package_prefix.replace(".", "/")}/{system_name.lower()}'

        # 扫描所有页面，每个页面独立生成 entity/repository/model/dto
        openapi_files = [f for f in os.listdir(sys_dir) if f.endswith('.json')]
        openapi_objs = []
        for file in openapi_files:
            page_name = os.path.splitext(file)[0]
            with open(os.path.join(sys_dir, file), encoding='utf-8') as f:
                openapi = json.load(f)
            openapi_objs.append((page_name, openapi))
            schemas = openapi.get('components', {}).get('schemas', {})
            page_schema_key = upper_camel(page_name)
            schema = schemas.get(page_schema_key, {})
            if not schema:
                print(f"[error] 未找到schema定义，schemas keys: {list(schemas.keys())}, page_schema_key: {page_schema_key}")
                continue
            fields = get_fields_from_schema(schema)
            # 【新增】用表名（而不是页面名）生成所有实体相关类名
            table_name = openapi.get('info', {}).get('tableName', page_name)
            model_class_name = upper_camel(table_name)   # 例：ODS_TRADE_INFO -> OdsTradeInfo
            system_package_name = f"{base_package}.{system_name.lower()}"  # com.hg.系统
            generate_entity_repository_model(env, backend_dir, java_root, model_class_name, fields, system_package_name, table_name)

        # 主类、yaml、readme
        app_java_dir = os.path.join(backend_dir, java_root)
        os.makedirs(app_java_dir, exist_ok=True)
        system_package_name = f"{base_package}.{system_name.lower()}"
        code = render_template(env, 'application.java.j2',
                            package_name=system_package_name,
                            app_class_name=app_class_name)
        with open(os.path.join(app_java_dir, f"{app_class_name}.java"), 'w', encoding='utf-8') as fw:
            fw.write(code)
        resource_dir = os.path.join(backend_dir, 'src/main/resources')
        os.makedirs(resource_dir, exist_ok=True)
        code = render_template(
            env, 'application.yml.j2', 
            system_name=system_name,         # <--- 关键
            # nacos_enabled='false',            # 是否使用 nacos
            # nacos_addr='192.168.50.101:8848',# nacos服务器指定
            # server_port=8080, # nacos服务器端口指定
            artifact_id=artifact_id
            )
        with open(os.path.join(resource_dir, 'application.yml'), 'w', encoding='utf-8') as fw:
            fw.write(code)
        code = render_template(env, 'readme.md.j2', package_name=base_package, artifact_id=artifact_id)
        with open(os.path.join(backend_dir, 'README.md'), 'w', encoding='utf-8') as fw:
            fw.write(code)
        # 页面级
        for page_name, openapi in openapi_objs:
            generate_for_page(env, backend_dir, java_root, system_name, page_name, openapi,
                            base_package, app_class_name, artifact_id)
        print(f"✅ 代码已输出到：{backend_dir}")

        # 一致性校验（仅做示例，可根据实际结构进一步丰富）
        expected_structure = [
            f"src/main/java/{args.package_prefix.replace('.', '/')}/{system_name.lower()}/entity",
            f"src/main/java/{args.package_prefix.replace('.', '/')}/{system_name.lower()}/repository",
            f"src/main/java/{args.package_prefix.replace('.', '/')}/{system_name.lower()}/model",
            f"src/main/java/{args.package_prefix.replace('.', '/')}/{system_name.lower()}/{openapi_objs[0][0]}/controller",
            f"src/main/java/{args.package_prefix.replace('.', '/')}/{system_name.lower()}/{openapi_objs[0][0]}/service",
            f"src/main/java/{args.package_prefix.replace('.', '/')}/{system_name.lower()}/{openapi_objs[0][0]}/service/impl",
            f"src/main/java/{args.package_prefix.replace('.', '/')}/{system_name.lower()}/{openapi_objs[0][0]}/dto",
        ]
        check_consistency(args.output_dir, system_name, expected_structure)

        # zip 打包
        if args.zip:
            zip_path = os.path.join(args.output_dir, f"{artifact_id}.zip")
            make_zip_dir(backend_dir, zip_path)


    # 导出 common-backend，仅用于平台全量交付（如有需要）
    # if args.with_common:
    #     src_common = os.path.join(args.templates_dir, 'common-backend')
    #     tgt_common = os.path.join(args.output_dir, 'common-backend')
    #     if os.path.exists(tgt_common):
    #         shutil.rmtree(tgt_common)
    #     shutil.copytree(src_common, tgt_common)
    #     print("✅ common-backend 已输出到：", tgt_common)

if __name__ == '__main__':
    main()
