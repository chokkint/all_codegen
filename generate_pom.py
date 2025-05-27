from pathlib import Path
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, TemplateError
import re
import sys

# 默认依赖及版本号
DEFAULT_SPRING_BOOT_VERSION = "3.2.6"
DEFAULT_SPRING_CLOUD_VERSION = "2023.0.2"
DEFAULT_SPRING_CLOUD_ALIBABA_VERSION = "2022.0.0.0"
DEFAULT_JAVA_VERSION = "17"

# 基础依赖（不重复添加）
ESSENTIAL_DEPENDENCIES = [
    {"groupId": "org.springframework.boot", "artifactId": "spring-boot-starter-data-jpa"},
    {"groupId": "org.springframework.boot", "artifactId": "spring-boot-starter-web"},
    {"groupId": "org.springframework.boot", "artifactId": "spring-boot-starter-validation"},
    {"groupId": "com.h2database", "artifactId": "h2", "scope": "runtime"},
    # {"groupId": "org.projectlombok", "artifactId": "lombok", "scope": "provided"},
    {"groupId": "jakarta.persistence", "artifactId": "jakarta.persistence-api", "scope": "provided"}
]

def remove_blank_lines(text):
    """去除多余空行，使生成的 pom.xml 更美观"""
    return re.sub(r'\n\s*\n+', '\n', text)

def merge_dependencies(user_deps, base_deps):
    """将用户依赖与基础依赖合并，去重（按 groupId+artifactId）"""
    seen = set()
    merged = []
    for dep in base_deps + user_deps:
        key = (dep.get("groupId"), dep.get("artifactId"))
        if key not in seen:
            merged.append(dep)
            seen.add(key)
    return merged

def generate_pom_with_template(
    output_base_dir: Path,
    system_name: str,
    template_path: Path,
    group_id,
    artifact_id,
    version,
    java_version=DEFAULT_JAVA_VERSION,
    spring_boot_version=DEFAULT_SPRING_BOOT_VERSION,
    spring_cloud_version=DEFAULT_SPRING_CLOUD_VERSION,
    spring_cloud_alibaba_version=DEFAULT_SPRING_CLOUD_ALIBABA_VERSION,
    dependencies=None,
    plugins=None,
    repositories=None,
):
    """
    根据 Jinja2 模板自动生成 pom.xml，输出到对应目录
    - output_base_dir: 输出根目录
    - system_name: 系统/模块名（将作为输出子目录）
    - template_path: Jinja2 pom.xml 模板文件
    - 其它参数均为 pom.xml 变量
    """
    try:
        # 路径检查及创建
        if not template_path.exists() or not template_path.is_file():
            print(f"[FATAL] 模板文件不存在: {template_path.resolve()}")
            sys.exit(1)
        output_dir = output_base_dir / system_name
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "pom.xml"

        # 合并依赖，去重
        all_dependencies = merge_dependencies(dependencies or [], ESSENTIAL_DEPENDENCIES)

        # Jinja2 环境初始化
        env = Environment(loader=FileSystemLoader(str(template_path.parent)), trim_blocks=True, lstrip_blocks=True)
        try:
            template = env.get_template(template_path.name)
        except TemplateNotFound:
            print(f"[ERROR] 未找到模板文件: {template_path.name}（路径: {template_path.parent}）")
            sys.exit(1)

        # 模板渲染
        try:
            pom_xml = template.render(
                group_id=group_id,
                artifact_id=artifact_id,
                version=version,
                java_version=java_version,
                spring_boot_version=spring_boot_version,
                spring_cloud_version=spring_cloud_version,
                spring_cloud_alibaba_version=spring_cloud_alibaba_version,
                dependencies=all_dependencies,
                plugins=plugins or [],
                repositories=repositories or [],
            )
        except TemplateError as e:
            print(f"[ERROR] 模板渲染出错: {e}")
            sys.exit(1)

        # 写入文件
        try:
            output_path.write_text(remove_blank_lines(pom_xml), encoding='utf-8')
            print(f"✅ pom.xml 已写入: {output_path.resolve()}")
        except Exception as e:
            print(f"[ERROR] 写入文件失败: {output_path.resolve()} - {e}")
            sys.exit(1)
    except Exception as e:
        print(f"[FATAL] 未知错误: {e}")
        sys.exit(1)

# ========== 示例调用 ==========
if __name__ == "__main__":
    # 可自定义依赖、插件、仓库配置
    dependencies = [
        {"groupId": "com.hg", "artifactId": "common-backend", "version": "1.0.0"},
        # 其它自定义依赖
    ]
    plugins = [
        {
            "groupId": "org.apache.maven.plugins",
            "artifactId": "maven-compiler-plugin",
            "version": "3.11.0",
            "configuration": "<release>17</release>"
        },
        # spring-boot-maven-plugin 推荐不写 version，除非有特殊需要
        {
            "groupId": "org.springframework.boot",
            "artifactId": "spring-boot-maven-plugin"
        }
    ]
    repositories = [
        {"id": "nexus-ods", "url": "http://192.168.50.126:8099/repository/maven-public/"}
    ]
    system_name = "test"

    generate_pom_with_template(
        output_base_dir=Path("./output"),
        system_name=system_name + "-backend",
        template_path=Path("./templates/pom.xml.j2"),
        group_id="com.hg",
        artifact_id="test-backend",
        version="1.0.0",
        dependencies=dependencies,
        plugins=plugins,
        repositories=repositories,
    )
