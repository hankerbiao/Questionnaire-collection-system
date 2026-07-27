from datetime import UTC, datetime
from functools import lru_cache
from typing import Literal

from app.survey_models import SurveyVersion

ROLE_LABELS = [
    ("leader", "测试部领导", "关注整体效率、质量与管理决策"),
    ("lab-bios", "Lab 负责人 - BIOS", "负责 BIOS Lab 流程与资源协同"),
    ("lab-bmc", "Lab 负责人 - BMC", "负责 BMC Lab 流程与资源协同"),
    ("lab-hw", "Lab 负责人 - HW", "负责 HW Lab 流程与资源协同"),
    ("lab-perf", "Lab 负责人 - Perf", "负责 Perf Lab 流程与资源协同"),
    ("lab-os", "Lab 负责人 - OS", "负责 OS Lab 流程与资源协同"),
    ("lab-tx", "Lab 负责人 - TX", "负责 TX Lab 流程与资源协同"),
    ("lab-zj", "Lab 负责人 - ZJ", "负责 ZJ Lab 流程与资源协同"),
    ("tpm-general", "通用项目 TPM", "负责通用项目推进与跨团队协作"),
    ("tpm-bytedance", "字节项目 TPM", "负责字节项目推进与跨团队协作"),
    ("tpm-alibaba", "阿里项目 TPM", "负责阿里项目推进与跨团队协作"),
    ("tpm-component", "部件项目 TPM", "负责部件项目推进与跨团队协作"),
    ("tester", "测试人员", "日常执行测试与记录结果"),
    ("automation", "自动化开发人员", "建设自动化能力与工具链"),
    ("case-editor", "测试用例 / 需求编辑人员", "维护需求、用例和模板"),
    ("data-interface", "数据消费和数据产生接口", "消费、生产或联动 DML 数据"),
]

PAGE_CATALOG = [
    ("home", "首页", "首页与协作", True, [
        ("home-notifications", "通知与待办", "查看通知、待测试任务与个人待办"),
        ("home-review-progress", "评审进度", "查看需求、用例及计划评审进度"),
        ("home-statistics", "个人与项目统计", "查看个人工作量和项目质量统计"),
        ("home-links", "常用外部链接", "快速访问常用系统和资料"),
    ]),
    ("requirements", "测试需求", "需求与用例", True, [
        ("requirements-search", "目录、搜索与筛选", "按目录、状态和标签定位需求"),
        ("requirements-detail", "详情、评论与附件", "维护需求内容、讨论和材料"),
        ("requirements-relations", "关联测试用例", "建立需求与用例的追溯关系"),
        ("requirements-review", "需求评审", "提交、审核和处理修改意见"),
        ("requirements-actions", "移动、复制与 Mantis", "复用需求并联动缺陷"),
    ]),
    ("test-cases", "测试用例", "需求与用例", True, [
        ("test-cases-search", "目录、标签与筛选", "按状态、评审、阶段和标签定位用例"),
        ("test-cases-edit", "用例编写与层次", "维护步骤、层级和测试阶段"),
        ("test-cases-import", "批量导入与维护", "导入、复制和批量更新用例"),
        ("test-cases-relations", "需求与用例关联", "管理需求、集合和用例关系"),
        ("test-cases-review", "用例评审", "提交、审核和跟踪修改"),
        ("test-cases-stats", "执行与缺陷统计", "查看执行结果、视频和 Mantis 数据"),
    ]),
    ("case-sets", "测试用例集合", "需求与用例", True, [
        ("case-sets-manage", "集合创建与维护", "创建、编辑和变更集合状态"),
        ("case-sets-members", "协作者与标签", "维护协作者、标签和权限范围"),
        ("case-sets-items", "需求与用例检索", "检索并加入需求或测试用例"),
        ("case-sets-status", "集合项状态", "跟踪集合内容的使用状态"),
        ("case-sets-plan", "自动计划条件", "配置生成测试计划的条件"),
    ]),
    ("projects", "项目列表", "项目执行", True, [
        ("projects-search", "项目查询与筛选", "按状态、类型和负责人定位项目"),
        ("projects-manage", "项目创建与维护", "维护项目信息、成员和生命周期"),
        ("projects-overview", "项目概览", "查看计划、需求、执行和风险概况"),
    ]),
    ("test-execution", "执行测试", "项目执行", True, [
        ("test-execution-queue", "待执行、已完成与统计", "切换任务队列并查看进度"),
        ("test-execution-config", "DUT 与配置检查", "确认被测对象和环境配置"),
        ("test-execution-result", "步骤与结果填写", "记录 Passed、Failed、Blocked 和耗时"),
        ("test-execution-evidence", "证据与附件", "上传日志、截图和执行证据"),
        ("test-execution-assignment", "任务分配", "分配、领取和转交执行任务"),
        ("test-execution-mantis", "Mantis 联动", "提交和跟踪执行中发现的缺陷"),
    ]),
    ("test-execution-excel", "执行测试（Excel版）", "项目执行", True, [
        ("test-execution-excel-import", "Excel 任务导入", "从 Excel 加载执行数据"),
        ("test-execution-excel-edit", "批量结果填写", "在表格中批量维护执行结果"),
        ("test-execution-excel-export", "结果导出", "导出执行结果和交付材料"),
    ]),
    ("mantis-reverse", "Mantis反查执行", "项目执行", True, [
        ("mantis-reverse-search", "缺陷反查", "通过 Mantis 缺陷定位关联执行记录"),
        ("mantis-reverse-detail", "关联详情", "查看用例、计划和执行上下文"),
    ]),
    ("benchmark-results", "基准测试结果", "项目执行", True, [
        ("benchmark-results-query", "结果查询", "按项目、平台和测试项筛选结果"),
        ("benchmark-results-compare", "基准对比", "对比版本、平台和历史数据"),
        ("benchmark-results-export", "结果导出", "导出基准数据用于分析"),
    ]),
    ("export-status", "数据导出状态", "实用工具", True, [
        ("export-status-progress", "导出任务进度", "查看排队、处理中、成功或失败状态"),
        ("export-status-download", "文件下载", "下载已完成的导出文件"),
        ("export-status-retry", "失败重试", "定位并重试失败任务"),
    ]),
    ("public-files", "公共文件", "实用工具", True, [
        ("public-files-manage", "文件上传与管理", "上传、下载、替换和删除公共文件"),
        ("public-files-search", "文件检索", "按名称、类型和时间查找文件"),
        ("public-files-sharing", "共享与引用", "在项目和测试工作中引用公共文件"),
    ]),
    ("component-summary", "部件测试汇总", "实用工具", True, [
        ("component-summary-filter", "汇总筛选", "按部件、项目和状态查看测试结果"),
        ("component-summary-analysis", "结果分析", "查看通过率、失败项和覆盖情况"),
        ("component-summary-export", "汇总导出", "导出部件测试汇总"),
    ]),
    ("execution-statistics", "测试执行统计", "实用工具", True, [
        ("execution-statistics-dashboard", "执行统计看板", "查看进度、结果和人员工作量"),
        ("execution-statistics-filter", "维度筛选", "按项目、计划、团队和时间分析"),
        ("execution-statistics-export", "统计导出", "导出统计数据和报表"),
    ]),
    ("byteeva-link", "ByteEVA数据联动", "实用工具", True, [
        ("byteeva-link-sync", "数据同步", "触发并查看 DML 与 ByteEVA 数据同步"),
        ("byteeva-link-mapping", "字段与对象映射", "维护两端数据关联关系"),
        ("byteeva-link-errors", "异常处理", "查看失败原因并重试联动任务"),
    ]),
    ("tags", "标签", "基础数据", True, [
        ("tags-manage", "标签维护", "创建、编辑、分类和停用标签"),
        ("tags-usage", "标签使用情况", "查看标签关联的需求、用例和项目"),
    ]),
    ("component-checkpoints", "部件检查点和物料组", "基础数据", True, [
        ("component-checkpoints-manage", "检查点维护", "创建和维护部件检查规则"),
        ("component-checkpoints-material", "物料组维护", "维护物料分组和关联关系"),
        ("component-checkpoints-import", "批量导入", "批量维护检查点和物料组"),
    ]),
    ("plan-name-components", "测试计划名称组件", "测试计划", True, [
        ("plan-name-components-manage", "名称组件维护", "创建、排序和停用命名组件"),
        ("plan-name-components-rules", "命名规则", "组合组件并校验计划名称"),
    ]),
    ("test-plan-management", "测试计划管理", "测试计划", True, [
        ("test-plan-management-crud", "计划创建与维护", "创建、编辑、复制和归档测试计划"),
        ("test-plan-management-filter", "计划查询与筛选", "按项目、平台、状态和负责人定位计划"),
        ("test-plan-management-content", "计划内容编排", "配置范围、用例、资源和排期"),
        ("test-plan-management-review", "平台与方案审核", "提交并跟踪测试计划审核"),
    ]),
    ("excel-template-management", "Excel测试模板管理", "Excel 管理", True, [
        ("excel-template-management-upload", "模板上传与版本", "上传、替换和管理 Excel 模板版本"),
        ("excel-template-management-config", "模板配置", "维护模板字段和适用范围"),
        ("excel-template-management-download", "模板下载", "检索并下载可用模板"),
    ]),
    ("excel-report-management", "Excel测试报告--上传和管理", "Excel 管理", True, [
        ("excel-report-management-upload", "报告上传", "上传并校验 Excel 测试报告"),
        ("excel-report-management-query", "报告查询", "按项目、计划和状态查找报告"),
        ("excel-report-management-review", "报告管理", "维护版本、状态并下载报告"),
    ]),
    ("excel-plan-management", "Excel测试计划管理", "Excel 管理", True, [
        ("excel-plan-management-upload", "计划上传", "上传并校验 Excel 测试计划"),
        ("excel-plan-management-query", "计划查询", "检索和筛选 Excel 测试计划"),
        ("excel-plan-management-sync", "计划同步", "同步计划数据与执行状态"),
    ]),
    ("tx-xh-cases", "Tx XH测试用例", "Excel 管理", False, [
        ("tx-xh-cases-access", "专项用例访问", "当前页面权限和功能待核实"),
    ]),
]


def _pages() -> list[dict[str, object]]:
    return [
        {
            "id": page_id,
            "name": name,
            "category": category,
            "order": page_order,
            "enabled": enabled,
            "features": [
                {"id": feature_id, "name": feature_name, "description": description, "order": order, "enabled": True}
                for order, (feature_id, feature_name, description) in enumerate(features, start=1)
            ],
        }
        for page_order, (page_id, name, category, enabled, features) in enumerate(PAGE_CATALOG, start=1)
    ]


@lru_cache
def _default_survey(
    status: Literal["draft", "published", "archived"],
    version: int,
    revision: int = 1,
) -> SurveyVersion:
    now = datetime.now(UTC)
    survey = SurveyVersion.model_validate(
        {
            "surveyKey": "dml-v4",
            "version": version,
            "status": status,
            "revision": revision,
            "title": "DML 使用体验调研",
            "description": "围绕常用页面、页面功能和真实问题收集可落地的改进反馈。",
            "roles": [
                {"id": role_id, "label": label, "description": description}
                for role_id, label, description in ROLE_LABELS
            ],
            "pages": _pages(),
            "createdAt": now,
            "updatedAt": now,
            "publishedAt": now if status == "published" else None,
        }
    )
    if status == "published":
        survey.validate_for_publish()
    return survey


def default_survey(
    status: Literal["draft", "published", "archived"],
    version: int,
    revision: int = 1,
) -> SurveyVersion:
    return _default_survey(status, version, revision).model_copy(deep=True)
