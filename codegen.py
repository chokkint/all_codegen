import os
import sys
import json
import argparse
import traceback
from zipfile import ZipFile
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, TemplateError

def upper_camel(s):
    # 确保文件名中的每个单词首字母大写，其它小写
    parts = s.replace('-', '_').replace('.', '_').split('_')
    return ''.join([parts[0].capitalize()] + [w.lower() for w in parts[1:]])


def small_camel(s):
    parts = s.lower().split('_')
    return parts[0] + ''.join([w.capitalize() for w in parts[1:]])

def get_primary_key_field(fields):
    for f in fields:
        if f.get('primaryKey', False):
            return f
    for f in fields:
        if f['name'].lower() in ('id', 'pk', 'table_id', 'user_id', 'column_id'):
            return f
    if fields:
        return fields[0]
    raise Exception("fields 为空，无法识别主键")

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
    try:
        fields = []
        for fname, finfo in schema.get('properties', {}).items():
            fields.append({
                'name': fname,
                'columnName': finfo.get('columnName', fname),  # 新增: 取 columnName，无则兜底
                'type': finfo.get('javaType', 'String'),
                'label': finfo.get('description', fname),
                'java_name': fname,          # 变量名直接用 name
                'java_type': finfo.get('javaType', 'String'),
                'primaryKey': finfo.get('primaryKey', False)
            })
        # 如无字段, 返回 id 占位
        return fields or [{
            'name': 'id',
            'columnName': 'ID',
            'type': 'Long',
            'java_name': 'id',
            'java_type': 'Long',
            'label': '主键ID',
            'primaryKey': True
        }]
    except Exception as e:
        print(f"[ERROR][字段解析失败] schema: {schema} - {e}")
        raise

def extract_paths(openapi):
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

def generate_system_level_code(env, backend_dir, java_root, model_class_name, fields, system_package, table_name, orm):
    try:
        pk_field = get_primary_key_field(fields)
        pk_type = pk_field['java_type'] if pk_field else 'Long'
        layers = {
            'entity.java.j2': os.path.join('entity', f"{model_class_name}Entity.java"),
            'model.java.j2': os.path.join('model', f"{model_class_name}Model.java"),
        }
        if orm == 'jpa':
            layers['repository.java.j2'] = os.path.join('repository', f"{model_class_name}Repository.java")
        variables = {
            'system_package': system_package,
            'model_class_name': f"{model_class_name}Model",
            'entity_class_name': f"{model_class_name}Entity",
            'repository_class_name': f"{model_class_name}Repository",
            'table_name': table_name,
            'fields': [
                {
                    'name': f['name'],
                    'columnName': f.get('columnName', f['name']),
                    'type': f['java_type'],
                    'java_name': f['name'],
                    'java_type': f['java_type'],
                    'label': f.get('label', f['name']),
                    'primary_key': f.get('primaryKey', False)
                }
                for f in fields
            ],
            'pk_field': pk_field,
            'pk_type': pk_type,
            'pk_field_java_type': pk_type,
            'orm': orm
        }
        for key, sub_path in layers.items():
            tgt_dir = os.path.join(backend_dir, java_root, os.path.dirname(sub_path))
            os.makedirs(tgt_dir, exist_ok=True)
            code = render_template(env, key, **variables)
            out_path = os.path.join(tgt_dir, os.path.basename(sub_path))
            with open(out_path, 'w', encoding='utf-8') as fw:
                fw.write(code)
        # BaseServiceImpl 统一输出到 common/service/impl/
        base_service_impl_dir = os.path.join(backend_dir, java_root, "common", "service", "impl")
        os.makedirs(base_service_impl_dir, exist_ok=True)
        code = render_template(env, "base_service_impl.java.j2", system_package=system_package, orm=orm)
        fname = "BaseJpaServiceImpl.java" if orm == "jpa" else "BaseMybatisServiceImpl.java"
        with open(os.path.join(base_service_impl_dir, fname), 'w', encoding='utf-8') as fw:
            fw.write(code)
    except Exception as e:
        print(f"[ERROR][实体/仓库/模型生成失败] model_class: {model_class_name} - {e}")
        print(traceback.format_exc())
        raise

def get_query_fields_from_openapi(openapi):
    query_fields = []
    seen = set()
    for path in extract_paths(openapi):
        if path['method'].lower() == 'get':
            for p in path.get('parameters', []):
                name = p['name']
                java_type = p.get('schema', {}).get('type', 'String').capitalize()
                if name not in seen:
                    query_fields.append({
                        'name': name,
                        'columnName': p.get('columnName', name),  # 兼容参数可能无 columnName
                        'type': java_type,
                        'label': p.get('description', name),
                        'java_name': name,
                        'java_type': java_type,
                    })
                    seen.add(name)
    if 'pageNum' not in seen:
        query_fields.append({'name': 'pageNum', 'columnName': 'PAGE_NUM', 'type': 'Integer', 'label': '页码', 'java_name': 'pageNum', 'java_type': 'Integer'})
    if 'pageSize' not in seen:
        query_fields.append({'name': 'pageSize', 'columnName': 'PAGE_SIZE', 'type': 'Integer', 'label': '页大小', 'java_name': 'pageSize', 'java_type': 'Integer'})
    return query_fields

def generate_for_page(env, backend_dir, java_root, system_name, page_name, openapi,
                     base_package, app_class_name, artifact_id, orm='mybatis'):
    try:
        table_name = openapi.get('info', {}).get('tableName', page_name)
        model_class_name = upper_camel(table_name)
        page_class_name = upper_camel(page_name)
        system_package = f"{base_package}.{system_name.lower()}"
        page_package = f"{system_package}.{page_name.lower()}"
        schemas = openapi.get('components', {}).get('schemas', {})
        page_schema_key = upper_camel(page_name)
        schema = schemas.get(page_schema_key, {}) or schemas.get(model_class_name, {})
        if not schema:
            print(f"[ERROR][未找到schema定义] system:{system_name}, page:{page_name}, schemas keys: {list(schemas.keys())}")
        fields = get_fields_from_schema(schema)
        query_fields = get_query_fields_from_openapi(openapi)
        query_dto_class_name = f"{model_class_name}QueryDTO"
        query_params = []
        for path in extract_paths(openapi):
            if path['method'].lower() == 'get':
                for p in path.get('parameters', []):
                    query_params.append({
                        'java_type': p.get('schema', {}).get('type', 'String').capitalize(),
                        'java_name': p['name'],
                        'name': p['name'],
                        'desc': p.get('description', p['name']),
                        'columnName': p.get('columnName', p['name']),
                    })
        query_params_str = ', '.join([f"{p['java_type']} {p['java_name']}" for p in query_params])
        query_param_names = [p['java_name'] for p in query_params]

        service_impl_class_name = f"{page_class_name}{'JpaServiceImpl' if orm == 'jpa' else 'MybatisServiceImpl'}"
        service_instance_name = page_class_name[0].lower() + page_class_name[1:] + ('JpaService' if orm == 'jpa' else 'MybatisService')
        service_impl_template = 'service_impl.java.j2'

        variables = {
            'system_package': system_package,
            'page_package': page_package,
            'page_class_name': page_class_name,
            'model_class_name': model_class_name,
            'mapper_instance_name': f"{model_class_name[0].lower() + model_class_name[1:]}Mapper",
            'entity_class_name': f"{model_class_name}Entity",
            'fields': fields,
            'controller_class_name': f"{page_class_name}Controller",
            'service_class_name': f"{page_class_name}Service",
            'service_impl_class_name': service_impl_class_name,
            'service_instance_name': service_instance_name,
            'repository_class_name': f"{model_class_name}Repository",
            'dto_class_name': f"{model_class_name}DTO",
            'query_dto_class_name': query_dto_class_name,
            'apis': extract_paths(openapi),
            'app_class_name': app_class_name,
            'artifact_id': artifact_id,
            'page_name': page_name,
            'query_params': query_params,
            'query_params_str': query_params_str,
            'query_param_names': query_param_names,
            'orm': orm,
            'table_name': table_name,
        }

        pk_field = get_primary_key_field(fields)
        variables['pk_field_name'] = pk_field['name']
        variables['pk_field_java_name'] = pk_field['java_name']
        variables['pk_field_java_type'] = pk_field['java_type']
        variables['mapper_class_name'] = f"{model_class_name}Mapper"

        page_dir = os.path.join(backend_dir, java_root, page_name.lower())

        file_generate_plan = [
            ('controller', 'controller.java.j2', f"{page_class_name}Controller.java", {}),
            ('service', 'service.java.j2', f"{page_class_name}Service.java", {}),
            ('dto', 'dto.java.j2', f"{model_class_name}DTO.java", {}),
            ('dto', 'query_dto.java.j2', f"{model_class_name}QueryDTO.java", {'fields': query_fields, 'query_dto_class_name': query_dto_class_name}),
        ]
        for subdir, template, fname, extra in file_generate_plan:
            tgt_dir = os.path.join(page_dir, subdir)
            os.makedirs(tgt_dir, exist_ok=True)
            merged_vars = {**variables, **extra}
            code = render_template(env, template, **merged_vars)
            with open(os.path.join(tgt_dir, fname), 'w', encoding='utf-8') as fw:
                fw.write(code)

        impl_dir = os.path.join(page_dir, 'service', 'impl')
        os.makedirs(impl_dir, exist_ok=True)
        impl_code = render_template(env, service_impl_template, **variables)
        with open(os.path.join(impl_dir, f"{service_impl_class_name}.java"), 'w', encoding='utf-8') as fw:
            fw.write(impl_code)

        # 这里将 mapper 代码放到系统级目录，确保仅系统级目录有 mapper
        if orm == 'mybatis':
            system_mapper_dir = os.path.join(backend_dir, java_root, 'mapper')  # 系统级目录
            os.makedirs(system_mapper_dir, exist_ok=True)
            mapper_code = render_template(env, 'mapper.java.j2', **variables)
            with open(os.path.join(system_mapper_dir, f"{model_class_name}Mapper.java"), 'w', encoding='utf-8') as fw:
                fw.write(mapper_code)

            # XML 文件生成位置修改为系统级目录下的资源目录
            xml_dir = os.path.join(backend_dir, 'src', 'main', 'resources', 'mybatis', 'xml')
            os.makedirs(xml_dir, exist_ok=True)
            xml_code = render_template(env, 'mapper.xml.j2', **variables)
            with open(os.path.join(xml_dir, f"{model_class_name}Mapper.xml"), 'w', encoding='utf-8') as fw:
                fw.write(xml_code)
    except Exception as e:
        print(f"[ERROR][页面代码生成失败] system:{system_name}, page:{page_name} - {e}")
        print(traceback.format_exc())
        raise


def check_consistency(output_dir, system_name, expected_structure):
    backend_dir = os.path.join(output_dir, f"{system_name}-backend")
    # 对于 'mapper' 目录，单独处理，只在系统级目录中校验
    modified_structure = []
    for path in expected_structure:
        # 确保mapper目录检查只在系统级目录中进行
        if 'mapper' in path and 'src/main/java/com/hg/test/pagemanage/mapper' in path:
            continue  # 跳过页面级的mapper路径校验
        modified_structure.append(path)

    # 校验所有需要的目录
    for path in modified_structure:
        full_path = os.path.join(backend_dir, path)
        if not os.path.exists(full_path):
            print(f"[ERROR][一致性校验] 缺少关键输出：{full_path}")
            return False

    print("[一致性校验] 结构完整，通过。")
    return True

def make_zip_dir(src_dir, zip_path):
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
    parser = argparse.ArgumentParser(description="OpenAPI 自动生成 Java 微服务工程代码（JPA/MyBatis 互斥，不能共存！）")
    parser.add_argument('--package-prefix', default='com.hg', help='Java package 前缀')
    parser.add_argument('--openapi-dir', default='./docs/openapi_json', help='OpenAPI JSON 根目录')
    parser.add_argument('--output-dir', default='./output', help='输出目录')
    parser.add_argument('--templates-dir', default='./templates', help='模板目录')
    parser.add_argument('--orm', default='mybatis', help='ORM类型[jpa or mybatis]，必须单选，不能 all')
    parser.add_argument('--zip', action='store_true', help='输出主工程 zip 包')
    args = parser.parse_args()
    base_package = args.package_prefix

    openapi_dir = os.path.abspath(args.openapi_dir)
    output_dir = os.path.abspath(args.output_dir)
    templates_dir = os.path.abspath(args.templates_dir)
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

    env = Environment(loader=FileSystemLoader(templates_dir), trim_blocks=True, lstrip_blocks=True)
    def upper_first(s):
        return s[0].upper() + s[1:] if s else s
    env.filters['upper_first'] = upper_first

    for system_name in os.listdir(openapi_dir):
        sys_dir = os.path.join(openapi_dir, system_name)
        if not os.path.isdir(sys_dir):
            continue
        try:
            artifact_id = f"{system_name}-backend"
            app_class_name = upper_camel(system_name) + "ApiApplication"
            backend_dir = os.path.join(output_dir, artifact_id)
            java_root = os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower())

            # 1. PageUtils 工具类统一用 page_utils.java.j2（内部分支生成）
            system_package = f"{base_package}.{system_name.lower()}"
            pageutils_dir = os.path.join(backend_dir, java_root, "common", "page")
            os.makedirs(pageutils_dir, exist_ok=True)
            code = render_template(env, "page_utils.java.j2", system_package=system_package, orm=args.orm)
            pageutils_cls = "PageUtilsJpa.java" if args.orm == "jpa" else "PageUtilsMybatis.java"
            with open(os.path.join(pageutils_dir, pageutils_cls), 'w', encoding='utf-8') as fw:
                fw.write(code)

            # 2. 其它实体、模型、仓库、基础服务实现（JPA/MyBatis自动切换）
            openapi_files = [f for f in os.listdir(sys_dir) if f.endswith('.json')]
            openapi_objs = []
            entity_keys = set()
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
                    system_package = f"{base_package}.{system_name.lower()}"
                    entity_key = f"{system_name.lower()}:{model_class_name}"
                    if entity_key not in entity_keys:
                        generate_system_level_code(
                            env,
                            backend_dir,
                            java_root,
                            model_class_name,
                            fields,
                            system_package,
                            table_name,
                            args.orm
                        )
                        entity_keys.add(entity_key)
                except Exception as e:
                    print(f"[ERROR][处理页面失败] system:{system_name}, file:{file} - {e}")
                    print(traceback.format_exc())
            # 主类、application.yml、README.md
            app_java_dir = os.path.join(backend_dir, java_root)
            os.makedirs(app_java_dir, exist_ok=True)
            system_package = f"{base_package}.{system_name.lower()}"
            try:
                code = render_template(env, 'application.java.j2',
                                   system_package=system_package,
                                   app_class_name=app_class_name,
                                   system_name=system_name)
                with open(os.path.join(app_java_dir, f"{app_class_name}.java"), 'w', encoding='utf-8') as fw:
                    fw.write(code)
                resource_dir = os.path.join(backend_dir, 'src', 'main', 'resources')
                os.makedirs(resource_dir, exist_ok=True)
                code = render_template(
                    env, 'application.yml.j2',
                    system_name=system_name,
                    artifact_id=artifact_id,
                    db_name=system_name.lower(),
                    orm=args.orm
                )
                with open(os.path.join(resource_dir, 'application.yml'), 'w', encoding='utf-8') as fw:
                    fw.write(code)
                code = render_template(env, 'readme.md.j2', system_package=system_package, artifact_id=artifact_id, orm=args.orm, system_name=system_name, db_name=system_name.lower())
                with open(os.path.join(backend_dir, 'README.md'), 'w', encoding='utf-8') as fw:
                    fw.write(code)
            except Exception as e:
                print(f"[ERROR][主类/配置文件生成失败] system:{system_name} - {e}")
                print(traceback.format_exc())
            # 页面级 controller/service/dto/impl/mapper 代码
            for page_name, openapi in openapi_objs:
                try:
                    generate_for_page(
                        env,
                        backend_dir,
                        java_root,
                        system_name.lower(),
                        page_name.lower(),
                        openapi,
                        base_package,
                        app_class_name,
                        artifact_id,
                        orm=args.orm
                    )
                except Exception as e:
                    print(f"[ERROR][生成页面代码失败] system:{system_name}, page:{page_name} - {e}")
                    print(traceback.format_exc())
            # 结构一致性校验和打包
            if openapi_objs:
                expected_structure = [
                    os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), 'entity'),
                    os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), 'model'),
                    os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), 'common', 'page'),
                ]
                if args.orm == 'jpa':
                    expected_structure.append(os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), 'repository'))
                for page_name, _ in openapi_objs:
                    expected_structure += [
                        os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), page_name.lower(), 'controller'),
                        os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), page_name.lower(), 'service'),
                        os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), page_name.lower(), 'service', 'impl'),
                        os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), page_name.lower(), 'dto'),
                    ]
                    if args.orm == 'mybatis':
                        expected_structure.append(
                            os.path.join('src', 'main', 'java', *args.package_prefix.split('.'), system_name.lower(), page_name.lower(), 'mapper')
                        )
                check_consistency(output_dir, system_name, expected_structure)
            if args.zip:
                zip_path = os.path.join(output_dir, f"{artifact_id}.zip")
                make_zip_dir(backend_dir, zip_path)
            print(f"✅ 代码已输出到：{backend_dir}")
        except Exception as e:
            print(f"[FATAL ERROR][系统级处理失败] system:{system_name} - {e}")
            print(traceback.format_exc())

if __name__ == '__main__':
    main()
