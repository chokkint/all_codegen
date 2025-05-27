import os
import sys
import json
import argparse
import shutil
from zipfile import ZipFile
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, TemplateError

def upper_camel(s):
    """下划线/中横线/点分隔字符串转为驼峰（首字母大写），如 'ods_trade_info' -> 'OdsTradeInfo'"""
    return ''.join([w.capitalize() for w in s.replace('-', '_').replace('.', '_').split('_')])

def small_camel(s):
    """下划线分隔字符串转为驼峰（首字母小写），如 'user_name' -> 'userName'"""
    parts = s.lower().split('_')
    return parts[0] + ''.join([w.capitalize() for w in parts[1:]])

def get_primary_key_field(fields):
    """优先找 primaryKey 字段，其次常用主键名，再兜底第一个字段"""
    for f in fields:
        if f.get('primaryKey', False):
            return f
    for f in fields:
        if f['name'].lower() in ('id', 'pk', 'trade_id', 'user_id', 'ods_id'):
            return f
    return fields[0] if fields else None

def package_from_path(system_name, page_name, base_package):
    """拼接 Java 包名，防止有空值"""
    segments = [base_package]
    if system_name:
        segments.append(system_name.lower())
    if page_name:
        segments.append(page_name.lower())
    return ".".join(segments)

def openapi_method_to_mapping(method):
    """将 HTTP 方法映射为 Spring 注解"""
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
    """渲染模板，并输出详细报错信息"""
    try:
        template = env.get_template(template_name)
        return template.render(**kwargs)
    except TemplateNotFound as e:
        print(f"[ERROR][模板未找到] 模板名: {template_name} - {e}")
        raise
    except TemplateError as e:
        print(f"[ERROR][模板渲染错误] 模板名: {template_name} - {e}")
        raise

def get_fields_from_schema(schema):
    """根据 schema 提取字段信息"""
    try:
        fields = []
        for fname, finfo in schema.get('properties', {}).items():
            fields.append({
                'name': fname,
                'type': finfo.get('javaType', 'String'),
                'label': finfo.get('description', fname),
                'java_name': small_camel(fname),
                'java_type': finfo.get('javaType', 'String'),
            })
        # 没有任何字段时兜底一个 id 字段
        return fields or [{'name': 'id', 'type': 'Long', 'java_name': 'id', 'java_type': 'Long', 'label': '主键ID'}]
    except Exception as e:
        print(f"[ERROR][字段解析失败] schema: {schema} - {e}")
        raise

def extract_paths(openapi):
    """提取 openapi 里的所有 API 路径信息"""
    try:
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
    except Exception as e:
        print(f"[ERROR][路径解析失败] openapi: {openapi} - {e}")
        raise

def generate_entity_repository_model(env, backend_dir, java_root, model_class_name, fields, package_prefix, table_name):
    """生成 entity、repository、model 层代码"""
    try:
        pk_field = get_primary_key_field(fields)
        pk_type = pk_field['java_type'] if pk_field else 'Long'
        layers = {
            'entity.java.j2': os.path.join('entity', f"{model_class_name}Entity.java"),
            'repository.java.j2': os.path.join('repository', f"{model_class_name}Repository.java"),
            'model.java.j2': os.path.join('model', f"{model_class_name}Model.java"),
        }
        variables = {
            'package_name': package_prefix,
            'model_class_name': f"{model_class_name}Model",
            'entity_class_name': f"{model_class_name}Entity",
            'repository_class_name': f"{model_class_name}Repository",
            'table_name': table_name,
            'fields': [
                {
                    'name': f['name'],
                    'db_column': f['name'],
                    'type': f['java_type'],
                    'java_name': f['java_name'],
                    'java_type': f['java_type'],
                    'label': f.get('label', f['java_name']),
                    'primary_key': f.get('primaryKey', False)
                }
                for f in fields
            ],
            'pk_type': pk_type
        }
        for key, sub_path in layers.items():
            tgt_dir = os.path.join(backend_dir, java_root, os.path.dirname(sub_path))
            os.makedirs(tgt_dir, exist_ok=True)
            code = render_template(env, key, **variables)
            out_path = os.path.join(tgt_dir, os.path.basename(sub_path))
            with open(out_path, 'w', encoding='utf-8') as fw:
                fw.write(code)
    except Exception as e:
        print(f"[ERROR][实体/仓库/模型生成失败] model_class: {model_class_name} - {e}")
        raise

def generate_for_page(env, backend_dir, java_root, system_name, page_name, openapi, base_package, app_class_name, artifact_id):
    """针对每个页面，生成 controller/service/impl/dto 层代码"""
    try:
        table_name = openapi.get('info', {}).get('tableName', page_name)
        model_class_name = upper_camel(table_name)
        page_class_name = upper_camel(page_name)
        page_package_name = package_from_path(system_name, page_name, base_package)
        schemas = openapi.get('components', {}).get('schemas', {})
        page_schema_key = upper_camel(page_name)
        schema = schemas.get(page_schema_key, {}) or schemas.get(model_class_name, {})
        if not schema:
            print(f"[ERROR][未找到schema定义] system:{system_name}, page:{page_name}, schemas keys: {list(schemas.keys())}")
        fields = get_fields_from_schema(schema)
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
        pk_field = get_primary_key_field(fields)
        variables['pk_field_name'] = pk_field['name']
        variables['pk_field_java_name'] = pk_field['java_name']
        variables['pk_field_java_type'] = pk_field['java_type']
        page_dir = os.path.join(backend_dir, java_root, page_name)
        controller_dir = os.path.join(page_dir, 'controller')
        os.makedirs(controller_dir, exist_ok=True)
        ctrl_code = render_template(env, 'controller.java.j2', **variables)
        with open(os.path.join(controller_dir, f"{page_class_name}Controller.java"), 'w', encoding='utf-8') as fw:
            fw.write(ctrl_code)
        service_dir = os.path.join(page_dir, 'service')
        os.makedirs(service_dir, exist_ok=True)
        service_code = render_template(env, 'service.java.j2', **variables)
        with open(os.path.join(service_dir, f"{page_class_name}Service.java"), 'w', encoding='utf-8') as fw:
            fw.write(service_code)
        impl_dir = os.path.join(service_dir, 'impl')
        os.makedirs(impl_dir, exist_ok=True)
        service_impl_code = render_template(env, 'serviceImpl.java.j2', **variables)
        with open(os.path.join(impl_dir, f"{page_class_name}ServiceImpl.java"), 'w', encoding='utf-8') as fw:
            fw.write(service_impl_code)
        dto_dir = os.path.join(page_dir, 'dto')
        os.makedirs(dto_dir, exist_ok=True)
        dto_code = render_template(env, 'dto.java.j2', **variables)
        with open(os.path.join(dto_dir, f"{model_class_name}DTO.java"), 'w', encoding='utf-8') as fw:
            fw.write(dto_code)
    except Exception as e:
        print(f"[ERROR][页面代码生成失败] system:{system_name}, page:{page_name} - {e}")
        raise

def check_consistency(output_dir, system_name, expected_structure):
    """简单检查输出结构是否完整"""
    backend_dir = os.path.join(output_dir, f"{system_name}-backend")
    for path in expected_structure:
        full_path = os.path.join(backend_dir, path)
        if not os.path.exists(full_path):
            print(f"[ERROR][一致性校验] 缺少关键输出：{full_path}")
            return False
    print("[一致性校验] 结构完整，通过。")
    return True

def make_zip_dir(src_dir, zip_path):
    """将指定目录打包为 zip 文件"""
    try:
        with ZipFile(zip_path, 'w') as zipf:
            for folder_name, subfolders, filenames in os.walk(src_dir):
                for filename in filenames:
                    file_path = os.path.join(folder_name, filename)
                    arcname = os.path.relpath(file_path, src_dir)
                    zipf.write(file_path, arcname)
        print(f"✅ 已生成工程 ZIP 包：{zip_path}")
    except Exception as e:
        print(f"[ERROR][打包zip失败] {zip_path} - {e}")
        raise

def main():
    """主入口，参数检查 + 路径校验 + 主流程调用"""
    parser = argparse.ArgumentParser(description="OpenAPI 自动生成 Java 微服务工程代码（跨平台版）")
    parser.add_argument('--package-prefix', default='com.hg', help='Java package 前缀')
    parser.add_argument('--openapi-dir', default='./docs/openapi_json', help='OpenAPI JSON 根目录')
    parser.add_argument('--output-dir', default='./output', help='输出目录')
    parser.add_argument('--templates-dir', default='./templates', help='模板目录')
    parser.add_argument('--zip', action='store_true', help='输出主工程 zip 包')
    args = parser.parse_args()
    base_package = args.package_prefix

    # 路径参数统一成绝对路径
    openapi_dir = os.path.abspath(args.openapi_dir)
    output_dir = os.path.abspath(args.output_dir)
    templates_dir = os.path.abspath(args.templates_dir)

    # 检查目录是否存在
    if not os.path.exists(openapi_dir) or not os.path.isdir(openapi_dir):
        print(f"[FATAL] openapi-dir 不存在或不是目录: {openapi_dir}")
        sys.exit(1)
    if not os.path.exists(templates_dir) or not os.path.isdir(templates_dir):
        print(f"[FATAL] templates-dir 不存在或不是目录: {templates_dir}")
        sys.exit(1)
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"[INFO] 自动创建输出目录: {output_dir}")
        except Exception as e:
            print(f"[FATAL] 无法创建输出目录: {output_dir} - {e}")
            sys.exit(1)

    # 初始化模板引擎
    env = Environment(loader=FileSystemLoader(templates_dir), trim_blocks=True, lstrip_blocks=True)
    def upper_first(s):
        return s[0].upper() + s[1:] if s else s
    env.filters['upper_first'] = upper_first

    # 主循环：遍历每个系统
    for system_name in os.listdir(openapi_dir):
        sys_dir = os.path.join(openapi_dir, system_name)
        if not os.path.isdir(sys_dir):
            continue  # 跳过文件
        try:
            artifact_id = f"{system_name}-backend"
            app_class_name = upper_camel(system_name) + "ApiApplication"
            backend_dir = os.path.join(output_dir, artifact_id)
            java_root = os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower())
            openapi_files = [f for f in os.listdir(sys_dir) if f.endswith('.json')]
            openapi_objs = []
            for file in openapi_files:
                page_name = os.path.splitext(file)[0]
                try:
                    file_path = os.path.join(sys_dir, file)
                    with open(file_path, encoding='utf-8') as f:
                        openapi = json.load(f)
                    openapi_objs.append((page_name, openapi))
                    schemas = openapi.get('components', {}).get('schemas', {})
                    page_schema_key = upper_camel(page_name)
                    schema = schemas.get(page_schema_key, {})
                    if not schema:
                        print(f"[ERROR][未找到schema定义] system:{system_name}, page:{page_name}, schemas keys: {list(schemas.keys())}, page_schema_key: {page_schema_key}")
                        continue
                    fields = get_fields_from_schema(schema)
                    table_name = openapi.get('info', {}).get('tableName', page_name)
                    model_class_name = upper_camel(table_name)
                    system_package_name = f"{base_package}.{system_name.lower()}"
                    generate_entity_repository_model(env, backend_dir, java_root, model_class_name, fields, system_package_name, table_name)
                except Exception as e:
                    print(f"[ERROR][处理页面失败] system:{system_name}, file:{file} - {e}")
            # 主类、yaml、readme 生成
            app_java_dir = os.path.join(backend_dir, java_root)
            os.makedirs(app_java_dir, exist_ok=True)
            system_package_name = f"{base_package}.{system_name.lower()}"
            try:
                code = render_template(env, 'application.java.j2',
                                   package_name=system_package_name,
                                   app_class_name=app_class_name)
                with open(os.path.join(app_java_dir, f"{app_class_name}.java"), 'w', encoding='utf-8') as fw:
                    fw.write(code)
                resource_dir = os.path.join(backend_dir, 'src', 'main', 'resources')
                os.makedirs(resource_dir, exist_ok=True)
                code = render_template(
                    env, 'application.yml.j2', 
                    system_name=system_name,
                    artifact_id=artifact_id
                )
                with open(os.path.join(resource_dir, 'application.yml'), 'w', encoding='utf-8') as fw:
                    fw.write(code)
                code = render_template(env, 'readme.md.j2', package_name=base_package, artifact_id=artifact_id)
                with open(os.path.join(backend_dir, 'README.md'), 'w', encoding='utf-8') as fw:
                    fw.write(code)
            except Exception as e:
                print(f"[ERROR][主类/配置文件生成失败] system:{system_name} - {e}")
            # 控制器、服务等页面级代码
            for page_name, openapi in openapi_objs:
                try:
                    generate_for_page(env, backend_dir, java_root, system_name, page_name, openapi,
                                     base_package, app_class_name, artifact_id)
                except Exception as e:
                    print(f"[ERROR][生成页面代码失败] system:{system_name}, page:{page_name} - {e}")
            # 检查结构
            if openapi_objs:
                expected_structure = [
                    os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), 'entity'),
                    os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), 'repository'),
                    os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), 'model'),
                    os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), openapi_objs[0][0], 'controller'),
                    os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), openapi_objs[0][0], 'service'),
                    os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), openapi_objs[0][0], 'service', 'impl'),
                    os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), openapi_objs[0][0], 'dto'),
                ]
                check_consistency(output_dir, system_name, expected_structure)
            if args.zip:
                zip_path = os.path.join(output_dir, f"{artifact_id}.zip")
                make_zip_dir(backend_dir, zip_path)
            print(f"✅ 代码已输出到：{backend_dir}")
        except Exception as e:
            print(f"[FATAL ERROR][系统级处理失败] system:{system_name} - {e}")

if __name__ == '__main__':
    main()
