from pathlib import Path
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, TemplateError
import re
import sys
import argparse

DEFAULT_SPRING_BOOT_VERSION = "3.2.6"
DEFAULT_SPRING_CLOUD_VERSION = "2023.0.2"
DEFAULT_SPRING_CLOUD_ALIBABA_VERSION = "2022.0.0.0"
DEFAULT_JAVA_VERSION = "17"

def remove_blank_lines(text: str) -> str:
    """去除多余空行，便于输出美观的XML"""
    return re.sub(r'\n\s*\n+', '\n', text)

def merge_dependencies(user_deps, base_deps):
    """合并去重依赖项，优先保留基础依赖，用户依赖不重复加入"""
    seen = set()
    merged = []
    for dep in base_deps + (user_deps or []):
        key = (dep.get("groupId"), dep.get("artifactId"))
        if key not in seen:
            merged.append(dep)
            seen.add(key)
    return merged

def get_orm_dependencies(orm: str):
    """根据ORM类型返回基础依赖列表"""
    base = [
        {"groupId": "org.springframework.boot", "artifactId": "spring-boot-starter-web"},
        {"groupId": "org.springframework.boot", "artifactId": "spring-boot-starter-validation"},
        {"groupId": "com.h2database", "artifactId": "h2", "scope": "runtime"},
        {"groupId": "com.mysql", "artifactId": "mysql-connector-j", "version": "8.3.0"},
        {"groupId": "com.hg", "artifactId": "common-backend", "version": "1.0.0"}
    ]
    if orm == 'mybatis':
        base.append({"groupId": "org.mybatis.spring.boot", "artifactId": "mybatis-spring-boot-starter", "version": "3.0.3"})
    elif orm == 'jpa':
        base.append({"groupId": "org.springframework.boot", "artifactId": "spring-boot-starter-data-jpa"})
        # base.append({"groupId": "jakarta.persistence", "artifactId": "jakarta.persistence-api", "scope": "provided"})
    return base

def generate_pom_with_template(
    output_base_dir: Path,
    system_name: str,
    template_path: Path,
    group_id: str,
    version: str,
    artifact_id: str = None,
    java_version: str = DEFAULT_JAVA_VERSION,
    spring_boot_version: str = DEFAULT_SPRING_BOOT_VERSION,
    spring_cloud_version: str = DEFAULT_SPRING_CLOUD_VERSION,
    spring_cloud_alibaba_version: str = DEFAULT_SPRING_CLOUD_ALIBABA_VERSION,
    dependencies=None,
    plugins=None,
    repositories=None,
):
    """
    生成 POM 文件主方法
    """
    try:
        if not template_path.exists() or not template_path.is_file():
            print(f"[FATAL] 模板文件不存在: {template_path.resolve()}")
            sys.exit(1)

        # 自动生成 artifactId，或支持外部自定义
        artifact_id = artifact_id or f"{system_name}-backend"
        output_dir = output_base_dir / artifact_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "pom.xml"

        # 初始化 Jinja2 模板环境
        env = Environment(loader=FileSystemLoader(str(template_path.parent)), trim_blocks=True, lstrip_blocks=True)
        try:
            template = env.get_template(template_path.name)
        except TemplateNotFound:
            print(f"[ERROR] 未找到模板文件: {template_path.name}（路径: {template_path.parent}）")
            sys.exit(1)

        # 模板渲染参数准备
        params = {
            "group_id": group_id,
            "artifact_id": artifact_id,
            "system_name": system_name,
            "version": version,
            "java_version": java_version,
            "spring_boot_version": spring_boot_version,
            "spring_cloud_version": spring_cloud_version,
            "spring_cloud_alibaba_version": spring_cloud_alibaba_version,
            "dependencies": dependencies,
            "plugins": plugins or [],
            "repositories": repositories or [],
        }

        try:
            pom_xml = template.render(**params)
        except TemplateError as e:
            print(f"[ERROR] 模板渲染出错: {e}")
            sys.exit(1)

        try:
            output_path.write_text(remove_blank_lines(pom_xml), encoding='utf-8')
            print(f"✅ pom.xml 已写入: {output_path.resolve()}")
        except Exception as e:
            print(f"[ERROR] 写入文件失败: {output_path.resolve()} - {e}")
            sys.exit(1)

    except Exception as e:
        print(f"[FATAL] 未知错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="自动生成 Java Spring Boot POM")
    parser.add_argument('--output-base-dir', default="./output", help='输出根目录')
    parser.add_argument('--system-name', required=True, help='系统名（artifactId将自动拼接为 system_name-backend）')
    parser.add_argument('--template-path', default="./templates/pom.xml.j2", help='pom.xml.j2 模板路径')
    parser.add_argument('--group-id', default="com.hg", help='groupId')
    parser.add_argument('--version', default="1.0.0", help='版本')
    parser.add_argument('--orm', default='mybatis', choices=['mybatis', 'jpa'], help='ORM模式[jpa or mybatis]（默认mybatis）')
    parser.add_argument('--artifact-id', default=None, help='自定义 artifactId，可选')
    # 可选：未来可扩展支持外部 dependencies/plugins/repositories 参数

    args = parser.parse_args()

    # 动态依赖组装
    base_deps = get_orm_dependencies(args.orm)
    # 用户自定义依赖：可扩展为从文件或参数读取
    user_deps = []  # 目前无，后续可扩展
    dependencies = merge_dependencies(user_deps, base_deps)

    # 默认插件（可通过参数扩展）
    plugins = [
        {
            "groupId": "org.apache.maven.plugins",
            "artifactId": "maven-compiler-plugin",
            "version": "3.11.0",
            "configuration": "<release>17</release>"
        },
        {
            "groupId": "org.springframework.boot",
            "artifactId": "spring-boot-maven-plugin"
        }
    ]
    # 默认仓库（可通过参数扩展）
    repositories = [
        {"id": "nexus-ods", "url": "http://45.153.131.127:8099/repository/maven-public/"}
    ]

    generate_pom_with_template(
        output_base_dir=Path(args.output_base_dir),
        system_name=args.system_name,
        template_path=Path(args.template_path),
        group_id=args.group_id,
        version=args.version,
        artifact_id=args.artifact_id,
        dependencies=dependencies,
        plugins=plugins,
        repositories=repositories,
    )
