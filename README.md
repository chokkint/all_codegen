1. 当然可以！下面是一份**专业版的 codegen 自动生成平台使用说明文档**，适合团队协作和内部文档，可直接放进你的 README 或平台帮助中心。

   ------

   # Java 业务代码自动生成平台（codegen.py）使用说明

   ## 一、功能简介

   本工具支持**根据 OpenAPI/Swagger JSON**（低代码/amis 等系统页面导出的 json），**一键自动生成企业级 Spring Boot 微服务代码**，输出包括：

   - 系统级 entity/dao/model
   - 页面级 controller/service/serviceImpl/dto
   - 标准应用主类、application.yml、README.md 等
   - 代码层级结构自动适配包名、系统名、页面名
   - 全部自动继承已部署的 common-backend 共通包基类
   - 支持多系统、多页面批量生成

   ------

   ## 二、目录结构要求

   ```text
   docs/openapi_json/
     ├── test/            # 系统目录（系统名=test）
     │   ├── page1.json   # 页面1的 openapi json
     │   └── page2.json   # 页面2的 openapi json
     ├── xxx/             # 其它系统
     │   └── ...
   ```

   ------

   ## 三、模板（templates）准备

   需在 `templates/` 目录下准备 jinja2 模板（`.j2` 文件），推荐包括：

   - entity.java.j2
   - dao.java.j2
   - model.java.j2
   - dto.java.j2
   - controller.java.j2
   - service.java.j2
   - serviceImpl.java.j2
   - Application.java.j2
   - application.yml.j2
   - README.md.j2

   > 最新模板详见你的文档/前述整理。

   ------

   ## 四、命令行参数说明

   ```sh
   python codegen.py \
       --package-prefix com.hg \
       --openapi-dir ./docs/openapi_json \
       --output-dir ./output \
       --templates-dir ./templates
   ```

   - `--package-prefix`：Java 顶级包名（如 com.hg）
   - `--openapi-dir`：OpenAPI JSON 根目录
   - `--output-dir`：代码输出主目录
   - `--templates-dir`：模板文件目录

   ------

   ## 五、自动生成流程

   1. **遍历 openapi-dir 下所有系统（每个子目录）**
   2. **每个系统目录下所有页面（json 文件）**
   3. **自动合并所有表的字段，系统级 entity/dao/model 只生成一份**
   4. **页面级 controller/service/serviceImpl/dto 独立分包生成**
   5. **所有类自动继承 com.hg.common.\* 基类**
   6. **自动输出主类（如 TestApiApplication.java）、application.yml、README.md**
   7. **结构举例（系统 test，页面 page2）：**

   ```text
   output/test-backend/
     ├── src/main/java/com/hg/test/
     │     ├── entity/OdsTradeInfoEntity.java
     │     ├── dao/OdsTradeInfoRepository.java
     │     ├── model/OdsTradeInfoModel.java
     │     ├── page2/
     │     │    ├── controller/Page2Controller.java
     │     │    ├── service/Page2Service.java
     │     │    ├── service/impl/Page2ServiceImpl.java
     │     │    └── dto/OdsTradeInfoDTO.java
     │     └── TestApiApplication.java
     ├── src/main/resources/application.yml
     └── README.md
   ```

   ------

   ## 六、共通包依赖

   - 自动生成的代码**不需要复制 common-backend.jar**，只需保证 pom.xml 里有如下依赖即可：

   ```xml
   <dependency>
       <groupId>com.hg</groupId>
       <artifactId>common-backend</artifactId>
       <version>1.0.0</version>
   </dependency>
   ```

   - 建议提前将 common-backend 发布至私有 Maven 仓库，并确保开发机 settings.xml 配置了仓库认证

   ------

   ## 七、注意事项

   - 所有模板可灵活定制，只需保证命名规范、变量一致
   - 字段类型/注释建议从 OpenAPI JSON 提取完整（如 description、javaType 等）
   - 业务代码和架构升级可直接改模板，主生成逻辑无需变更
   - 如需扩展 Swagger 注解、lombok、业务自定义注解，只需在模板里扩展
   - 多系统/多页面批量生成，输出互不干扰，字段合并递增，避免冲突

   ------

   ## 八、常见问题

   1. **jar 包依赖拉不到？**
      请检查 pom.xml 中 `<repositories>` 配置是否包含你的私服地址，settings.xml 是否有认证。
   2. **新加基类或通用能力？**
      只需升级 common-backend 并发布新版本，自动生成的业务系统改下 pom 版本即可。
   3. **模板找不到变量？**
      检查 codegen.py 里变量传递和模板变量名是否一致。
   4. **支持哪些数据库/中间件？**
      pom.xml 依赖可后续在导出工程环节拼接，不影响业务代码生成。

   ------

   ## 九、推荐流程

   1. 准备好 openapi json、模板和 common-backend 依赖
   2. 运行 codegen.py 一键生成全部业务工程
   3. 检查/补充 pom.xml 依赖
   4. 业务开发只需关注业务代码，无需关心基类和基础架构
   5. 可持续维护模板、通用包与自动生成主流程





# Shell命令


#### 1. 只生成 pnx-backend 工程到 output 目录（标准日常开发/测试/集成流程）
python codegen.py \
  --openapi-dir ./docs/openapi_json \
  --output-dir ./output \
  --templates-dir ./templates \
  --package-prefix com.hg

#### 2. 生成 pnx-backend 并自动打包为 zip（output/pnx-backend.zip，适合归档/交付/一键分发）
python codegen.py \
  --openapi-dir ./docs/openapi_json \
  --output-dir ./output \
  --templates-dir ./templates \
  --package-prefix com.hg \
  --zip



