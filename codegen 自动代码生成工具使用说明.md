# codegen 自动代码生成工具使用说明

------

## 一、准备环境

### 1. 安装 Python 3.8 及以上

确保本机已安装 Python 3.8 或更高版本。
查看版本：

```bash
python3 --version
```

### 2. 创建虚拟环境

在项目目录下执行：

```bash
python3 -m venv venv
```

- 会生成一个名为 `venv` 的虚拟环境目录。

### 3. 激活虚拟环境

- **Mac/Linux:**

  ```bash
  source venv/bin/activate
  ```

- **Windows:**

  ```bash
  venv\Scripts\activate
  ```

> 激活后命令行前面会出现 `(venv)` 前缀。

### 4. 升级 pip（可选）

```bash
pip install --upgrade pip
```

### 5. 安装依赖包

如项目目录下有 `requirements.txt` 文件：

```bash
pip install -r requirements.txt
```

如果没有，可手动安装主要依赖：

```bash
pip install jinja2
```

如需其它包可在 requirements.txt 增加。

**示例 requirements.txt：**

```
jinja2>=3.0
```

------

## 二、准备模板与数据

1. **OpenAPI JSON**
   把待生成系统的 openapi json 文件（如 `page1.json`, `page2.json`）按系统分文件夹，放在 `./docs/openapi_json/` 下：

   ```
   docs/
     openapi_json/
       test/
         page1.json
         page2.json
       prod/
         page1.json
   ```

2. **模板目录**
   模板建议放在 `./templates/` 下，如 `application.yml.j2`、`controller.java.j2` 等。

------

## 三、运行 codegen 工具

**基本用法：**

```bash
python codegen.py \
  --package-prefix com.hg \
  --openapi-dir ./docs/openapi_json \
  --output-dir ./output \
  --templates-dir ./templates \
  --nacos_enabled false \
  --nacos_addr 127.0.0.1:8848 \
  --server_port 8080 \
  --system_name test \
  --zip
```

### 参数说明

| 参数             | 说明                              |
| ---------------- | --------------------------------- |
| --package-prefix | Java 包名前缀（如 `com.hg`）      |
| --openapi-dir    | OpenAPI JSON 文件根目录           |
| --output-dir     | 代码输出目录                      |
| --templates-dir  | Jinja2 模板目录                   |
| --nacos_enabled  | 是否启用 nacos 注册（true/false） |
| --nacos_addr     | nacos 服务端地址                  |
| --server_port    | SpringBoot 端口                   |
| --system_name    | 系统名称，用于生成项目名          |
| --zip            | 生成 zip 包（可选）               |

**注意：**

- `system_name` 在批量生成时可不用传，codegen 会自动遍历 openapi 目录。
- `nacos_enabled=false` 表示本地调试不连接 nacos。

------

## 四、输出结构

生成的项目代码会在 `output/` 目录下，比如：

```
output/
  test-backend/
    src/
      main/
        java/
        resources/
          application.yml
    README.md
  test-backend.zip
```

------

## 五、常见问题排查

1. **application.yml 只显示 -backend，没有系统名？**
   - 请确认 codegen.py 渲染模板时有传递 `system_name=system_name` 参数。
2. **生成文件乱码/格式错乱？**
   - 确认模板用 UTF-8 编码，Python 写文件加 `encoding='utf-8'`。
3. **Jinja2 模板变量没替换？**
   - 检查传入参数名是否与模板一致。
4. **依赖找不到/ImportError？**
   - 请确保已激活虚拟环境再运行 `pip install` 和 codegen。
5. **生成 zip 包报错？**
   - 检查目录路径，或手动删掉 output 目录后重试。

------

## 六、完整流程举例

```bash
# 1. 创建并激活虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows用 venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt
# 或手动安装
pip install jinja2

# 3. 运行 codegen 自动生成
python codegen.py \
  --package-prefix com.hg \
  --openapi-dir ./docs/openapi_json \
  --output-dir ./output \
  --templates-dir ./templates \
  --nacos_enabled false \
  --server_port 8080 \
  --zip

# 4. 查看输出目录和日志
ls output/
```

------

## 七、结束和退出

用完后可退出虚拟环境：

```bash
deactivate
```

------

