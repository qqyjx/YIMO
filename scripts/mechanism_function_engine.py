#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
机理函数引擎 - Mechanism Function Engine
YIMO 对象生命周期管理器核心模块

功能：
1. 物理公式管理（如 P=UI, 损耗计算等）
2. 业务规则引擎（规则校验、条件判断）
3. 计算规则执行
4. 规则执行日志记录
5. 财务审计红线预警
"""

import os
import sys
import json
import uuid
import math
import re
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from decimal import Decimal, InvalidOperation

# 数据库连接
try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
except ImportError:
    mysql = None

# 安全的数学表达式求值
import ast
import operator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================================
# 安全表达式求值器
# ============================================================================

class SafeExpressionEvaluator:
    """安全的数学表达式求值器（防止代码注入）"""

    # 允许的运算符
    OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    # 允许的数学函数
    MATH_FUNCTIONS = {
        'abs': abs,
        'round': round,
        'min': min,
        'max': max,
        'sum': sum,
        'sqrt': math.sqrt,
        'pow': math.pow,
        'log': math.log,
        'log10': math.log10,
        'exp': math.exp,
        'sin': math.sin,
        'cos': math.cos,
        'tan': math.tan,
        'pi': math.pi,
        'e': math.e,
    }

    def __init__(self, variables: Dict[str, Any] = None):
        self.variables = variables or {}

    def evaluate(self, expression: str) -> Any:
        """安全求值表达式"""
        try:
            # 预处理：替换中文运算符
            expression = expression.replace('×', '*').replace('÷', '/').replace('＝', '=')

            # 解析AST
            tree = ast.parse(expression, mode='eval')

            # 求值
            return self._eval_node(tree.body)
        except Exception as e:
            logger.error(f"表达式求值失败: {expression}, 错误: {e}")
            raise ValueError(f"表达式求值失败: {e}")

    def _eval_node(self, node: ast.AST) -> Any:
        """递归求值AST节点"""
        if isinstance(node, ast.Constant):  # Python 3.8+
            return node.value
        elif isinstance(node, ast.Num):  # Python 3.7
            return node.n
        elif isinstance(node, ast.Str):  # Python 3.7
            return node.s
        elif isinstance(node, ast.Name):
            name = node.id
            if name in self.variables:
                return self.variables[name]
            elif name in self.MATH_FUNCTIONS:
                return self.MATH_FUNCTIONS[name]
            else:
                raise ValueError(f"未定义的变量: {name}")
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self.OPERATORS:
                raise ValueError(f"不支持的运算符: {op_type}")
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            return self.OPERATORS[op_type](left, right)
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in self.OPERATORS:
                raise ValueError(f"不支持的一元运算符: {op_type}")
            operand = self._eval_node(node.operand)
            return self.OPERATORS[op_type](operand)
        elif isinstance(node, ast.Call):
            func = self._eval_node(node.func)
            if not callable(func):
                raise ValueError(f"不可调用的函数")
            args = [self._eval_node(arg) for arg in node.args]
            return func(*args)
        elif isinstance(node, ast.Compare):
            # 支持比较运算
            left = self._eval_node(node.left)
            result = True
            for op, comp in zip(node.ops, node.comparators):
                right = self._eval_node(comp)
                if isinstance(op, ast.Lt):
                    result = result and (left < right)
                elif isinstance(op, ast.LtE):
                    result = result and (left <= right)
                elif isinstance(op, ast.Gt):
                    result = result and (left > right)
                elif isinstance(op, ast.GtE):
                    result = result and (left >= right)
                elif isinstance(op, ast.Eq):
                    result = result and (left == right)
                elif isinstance(op, ast.NotEq):
                    result = result and (left != right)
                else:
                    raise ValueError(f"不支持的比较运算符: {type(op)}")
                left = right
            return result
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(self._eval_node(v) for v in node.values)
            elif isinstance(node.op, ast.Or):
                return any(self._eval_node(v) for v in node.values)
        elif isinstance(node, ast.IfExp):
            if self._eval_node(node.test):
                return self._eval_node(node.body)
            else:
                return self._eval_node(node.orelse)
        else:
            raise ValueError(f"不支持的节点类型: {type(node)}")

# ============================================================================
# 机理函数类型
# ============================================================================

class FunctionType(Enum):
    """机理函数类型"""
    PHYSICAL = "physical"           # 物理公式
    BUSINESS = "business"           # 业务规则
    VALIDATION = "validation"       # 校验规则
    CALCULATION = "calculation"     # 计算规则
    TRANSFORMATION = "transformation" # 转换规则
    ROUTING = "routing"             # 路由规则

class RuleResult(Enum):
    """规则执行结果"""
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    ERROR = "error"
    SKIP = "skip"

@dataclass
class FunctionExecutionResult:
    """函数执行结果"""
    success: bool
    result: Any = None
    message: str = ""
    execution_time_ms: int = 0
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RuleExecutionResult:
    """规则执行结果"""
    rule_code: str
    status: RuleResult
    message: str = ""
    current_value: Any = None
    expected_value: Any = None
    execution_time_ms: int = 0
    triggered_actions: List[Dict] = field(default_factory=list)

# ============================================================================
# 内置物理公式
# ============================================================================

class PhysicalFormulas:
    """内置电力系统物理公式库"""

    @staticmethod
    def power_from_ui(voltage: float, current: float) -> float:
        """功率计算: P = U × I"""
        return voltage * current

    @staticmethod
    def power_from_ri(resistance: float, current: float) -> float:
        """功率计算: P = I² × R"""
        return current * current * resistance

    @staticmethod
    def power_from_ur(voltage: float, resistance: float) -> float:
        """功率计算: P = U² / R"""
        return voltage * voltage / resistance

    @staticmethod
    def line_loss(current: float, resistance: float) -> float:
        """线损计算: ΔP = I² × R"""
        return current * current * resistance

    @staticmethod
    def line_loss_rate(loss: float, total_power: float) -> float:
        """线损率计算: 线损率 = ΔP / P × 100%"""
        if total_power == 0:
            return 0
        return (loss / total_power) * 100

    @staticmethod
    def transformer_efficiency(output_power: float, input_power: float) -> float:
        """变压器效率: η = Pout / Pin × 100%"""
        if input_power == 0:
            return 0
        return (output_power / input_power) * 100

    @staticmethod
    def reactive_power(apparent_power: float, active_power: float) -> float:
        """无功功率: Q = √(S² - P²)"""
        if apparent_power < active_power:
            return 0
        return math.sqrt(apparent_power ** 2 - active_power ** 2)

    @staticmethod
    def power_factor(active_power: float, apparent_power: float) -> float:
        """功率因数: cosφ = P / S"""
        if apparent_power == 0:
            return 0
        return active_power / apparent_power

    @staticmethod
    def voltage_drop(current: float, resistance: float, reactance: float, power_factor: float) -> float:
        """电压降落: ΔU = I × (R × cosφ + X × sinφ)"""
        sin_phi = math.sqrt(1 - power_factor ** 2) if power_factor <= 1 else 0
        return current * (resistance * power_factor + reactance * sin_phi)

    @staticmethod
    def depreciation_straight_line(original_value: float, salvage_value: float, useful_life: int) -> float:
        """直线折旧法: 年折旧额 = (原值 - 残值) / 使用年限"""
        if useful_life <= 0:
            return 0
        return (original_value - salvage_value) / useful_life

# ============================================================================
# 机理函数引擎
# ============================================================================

class MechanismFunctionEngine:
    """机理函数引擎"""

    def __init__(self, db_connection=None):
        self.db = db_connection
        self.formula_registry: Dict[str, Callable] = {}
        self.rule_cache: Dict[str, Dict] = {}

        # 注册内置物理公式
        self._register_builtin_formulas()

    def _register_builtin_formulas(self):
        """注册内置物理公式"""
        builtin = PhysicalFormulas()

        self.register_formula('POWER_UI', builtin.power_from_ui,
            description='功率计算: P = U × I',
            inputs=[{'name': 'voltage', 'unit': 'V'}, {'name': 'current', 'unit': 'A'}],
            outputs=[{'name': 'power', 'unit': 'W'}])

        self.register_formula('POWER_RI', builtin.power_from_ri,
            description='功率计算: P = I² × R',
            inputs=[{'name': 'resistance', 'unit': 'Ω'}, {'name': 'current', 'unit': 'A'}],
            outputs=[{'name': 'power', 'unit': 'W'}])

        self.register_formula('LINE_LOSS', builtin.line_loss,
            description='线损计算: ΔP = I² × R',
            inputs=[{'name': 'current', 'unit': 'A'}, {'name': 'resistance', 'unit': 'Ω'}],
            outputs=[{'name': 'loss', 'unit': 'W'}])

        self.register_formula('LINE_LOSS_RATE', builtin.line_loss_rate,
            description='线损率计算',
            inputs=[{'name': 'loss', 'unit': 'W'}, {'name': 'total_power', 'unit': 'W'}],
            outputs=[{'name': 'rate', 'unit': '%'}])

        self.register_formula('TRANSFORMER_EFFICIENCY', builtin.transformer_efficiency,
            description='变压器效率计算',
            inputs=[{'name': 'output_power', 'unit': 'W'}, {'name': 'input_power', 'unit': 'W'}],
            outputs=[{'name': 'efficiency', 'unit': '%'}])

        self.register_formula('REACTIVE_POWER', builtin.reactive_power,
            description='无功功率计算: Q = √(S² - P²)',
            inputs=[{'name': 'apparent_power', 'unit': 'VA'}, {'name': 'active_power', 'unit': 'W'}],
            outputs=[{'name': 'reactive_power', 'unit': 'var'}])

        self.register_formula('POWER_FACTOR', builtin.power_factor,
            description='功率因数计算: cosφ = P / S',
            inputs=[{'name': 'active_power', 'unit': 'W'}, {'name': 'apparent_power', 'unit': 'VA'}],
            outputs=[{'name': 'power_factor', 'unit': ''}])

        self.register_formula('DEPRECIATION', builtin.depreciation_straight_line,
            description='直线折旧法年折旧额',
            inputs=[
                {'name': 'original_value', 'unit': 'CNY'},
                {'name': 'salvage_value', 'unit': 'CNY'},
                {'name': 'useful_life', 'unit': '年'}
            ],
            outputs=[{'name': 'annual_depreciation', 'unit': 'CNY'}])

    def register_formula(
        self,
        code: str,
        func: Callable,
        description: str = "",
        inputs: List[Dict] = None,
        outputs: List[Dict] = None
    ):
        """注册公式到引擎"""
        self.formula_registry[code] = {
            'function': func,
            'description': description,
            'inputs': inputs or [],
            'outputs': outputs or []
        }
        logger.debug(f"注册公式: {code}")

    def execute_formula(
        self,
        code: str,
        parameters: Dict[str, Any]
    ) -> FunctionExecutionResult:
        """执行已注册的公式"""
        start_time = datetime.now()

        if code not in self.formula_registry:
            return FunctionExecutionResult(
                success=False,
                message=f"未找到公式: {code}"
            )

        formula = self.formula_registry[code]
        func = formula['function']

        try:
            # 提取参数
            import inspect
            sig = inspect.signature(func)
            args = []
            for param_name in sig.parameters:
                if param_name not in parameters:
                    return FunctionExecutionResult(
                        success=False,
                        message=f"缺少参数: {param_name}"
                    )
                args.append(parameters[param_name])

            # 执行函数
            result = func(*args)

            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)

            return FunctionExecutionResult(
                success=True,
                result=result,
                message="执行成功",
                execution_time_ms=execution_time,
                input_data=parameters,
                output_data={'result': result}
            )

        except Exception as e:
            return FunctionExecutionResult(
                success=False,
                message=f"执行失败: {str(e)}",
                input_data=parameters
            )

    def execute_expression(
        self,
        expression: str,
        variables: Dict[str, Any]
    ) -> FunctionExecutionResult:
        """执行数学表达式"""
        start_time = datetime.now()

        try:
            evaluator = SafeExpressionEvaluator(variables)
            result = evaluator.evaluate(expression)

            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)

            return FunctionExecutionResult(
                success=True,
                result=result,
                message="表达式执行成功",
                execution_time_ms=execution_time,
                input_data=variables,
                output_data={'result': result}
            )

        except Exception as e:
            return FunctionExecutionResult(
                success=False,
                message=f"表达式执行失败: {str(e)}",
                input_data=variables
            )

    def get_formula_list(self) -> List[Dict]:
        """获取所有已注册的公式列表"""
        return [
            {
                'code': code,
                'description': info['description'],
                'inputs': info['inputs'],
                'outputs': info['outputs']
            }
            for code, info in self.formula_registry.items()
        ]

# ============================================================================
# 业务规则引擎
# ============================================================================

class BusinessRuleEngine:
    """业务规则引擎"""

    def __init__(self, db_connection=None):
        self.db = db_connection
        self.rule_cache: Dict[str, Dict] = {}
        self.redline_cache: Dict[str, Dict] = {}

    def load_rules_from_db(self):
        """从数据库加载业务规则"""
        if not self.db:
            logger.warning("数据库连接不可用，无法加载规则")
            return

        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM business_rules WHERE is_active = 1
            """)
            rules = cursor.fetchall()

            for rule in rules:
                self.rule_cache[rule['rule_code']] = rule

            logger.info(f"加载了 {len(rules)} 条业务规则")
            cursor.close()

        except Exception as e:
            logger.error(f"加载业务规则失败: {e}")

    def load_redlines_from_db(self):
        """从数据库加载财务审计红线"""
        if not self.db:
            logger.warning("数据库连接不可用，无法加载红线")
            return

        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM finance_audit_redlines WHERE is_active = 1
            """)
            redlines = cursor.fetchall()

            for redline in redlines:
                self.redline_cache[redline['redline_code']] = redline

            logger.info(f"加载了 {len(redlines)} 条审计红线")
            cursor.close()

        except Exception as e:
            logger.error(f"加载审计红线失败: {e}")

    def check_redline(
        self,
        redline_code: str,
        value: Any,
        context: Dict[str, Any] = None
    ) -> RuleExecutionResult:
        """检查审计红线"""
        start_time = datetime.now()

        if redline_code not in self.redline_cache:
            return RuleExecutionResult(
                rule_code=redline_code,
                status=RuleResult.ERROR,
                message=f"未找到红线规则: {redline_code}"
            )

        redline = self.redline_cache[redline_code]

        try:
            threshold = float(redline.get('threshold_value', 0))
            operator_type = redline.get('comparison_operator', 'gt')

            # 转换值
            if isinstance(value, str):
                try:
                    value = float(value.replace(',', ''))
                except:
                    pass

            # 比较运算
            triggered = False
            if operator_type == 'gt':
                triggered = value > threshold
            elif operator_type == 'gte':
                triggered = value >= threshold
            elif operator_type == 'lt':
                triggered = value < threshold
            elif operator_type == 'lte':
                triggered = value <= threshold
            elif operator_type == 'eq':
                triggered = value == threshold
            elif operator_type == 'neq':
                triggered = value != threshold
            elif operator_type == 'between':
                range_val = json.loads(redline.get('threshold_range', '[]'))
                if len(range_val) >= 2:
                    triggered = range_val[0] <= value <= range_val[1]

            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)

            if triggered:
                # 解析触发动作
                trigger_action = json.loads(redline.get('trigger_action', '{}'))

                return RuleExecutionResult(
                    rule_code=redline_code,
                    status=RuleResult.WARNING if redline.get('severity') == 'warning' else RuleResult.FAIL,
                    message=f"触发红线: {redline.get('redline_name')}",
                    current_value=value,
                    expected_value=f"{operator_type} {threshold} {redline.get('threshold_unit', '')}",
                    execution_time_ms=execution_time,
                    triggered_actions=[trigger_action] if trigger_action else []
                )
            else:
                return RuleExecutionResult(
                    rule_code=redline_code,
                    status=RuleResult.PASS,
                    message="未触发红线",
                    current_value=value,
                    expected_value=threshold,
                    execution_time_ms=execution_time
                )

        except Exception as e:
            return RuleExecutionResult(
                rule_code=redline_code,
                status=RuleResult.ERROR,
                message=f"红线检查失败: {str(e)}"
            )

    def evaluate_rule(
        self,
        rule_code: str,
        data: Dict[str, Any]
    ) -> RuleExecutionResult:
        """评估业务规则"""
        start_time = datetime.now()

        if rule_code not in self.rule_cache:
            return RuleExecutionResult(
                rule_code=rule_code,
                status=RuleResult.ERROR,
                message=f"未找到规则: {rule_code}"
            )

        rule = self.rule_cache[rule_code]

        try:
            # 解析规则要素
            rule_elements = json.loads(rule.get('rule_elements', '[]'))
            element_logic = rule.get('element_logic', 'and')

            if not rule_elements:
                return RuleExecutionResult(
                    rule_code=rule_code,
                    status=RuleResult.SKIP,
                    message="规则无要素定义"
                )

            # 评估每个要素
            element_results = []
            for element in rule_elements:
                element_name = element.get('name', '')
                element_logic_expr = element.get('logic', '')
                element_value = element.get('value', '')

                # 从数据中获取对应值
                actual_value = data.get(element_name)

                if actual_value is not None and element_logic_expr:
                    # 简单的条件评估
                    try:
                        evaluator = SafeExpressionEvaluator({
                            'value': actual_value,
                            'threshold': float(element_value) if element_value else 0
                        })
                        result = evaluator.evaluate(element_logic_expr)
                        element_results.append(result)
                    except:
                        element_results.append(True)  # 默认通过
                else:
                    element_results.append(True)

            # 根据逻辑关系组合结果
            if element_logic == 'and':
                final_pass = all(element_results)
            elif element_logic == 'or':
                final_pass = any(element_results)
            else:
                final_pass = all(element_results)

            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)

            return RuleExecutionResult(
                rule_code=rule_code,
                status=RuleResult.PASS if final_pass else RuleResult.FAIL,
                message=rule.get('result_value', '') if final_pass else f"规则验证失败: {rule.get('rule_name')}",
                execution_time_ms=execution_time
            )

        except Exception as e:
            return RuleExecutionResult(
                rule_code=rule_code,
                status=RuleResult.ERROR,
                message=f"规则评估失败: {str(e)}"
            )

    def log_execution(
        self,
        result: RuleExecutionResult,
        target_instance_uid: str = None,
        trigger_type: str = 'auto',
        trigger_event: str = None
    ):
        """记录规则执行日志"""
        if not self.db:
            return

        try:
            cursor = self.db.cursor()
            sql = """
                INSERT INTO rule_executions
                (execution_uid, rule_code, trigger_type, trigger_event,
                 target_instance_uid, input_data, output_data,
                 result_status, result_message, execution_time_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                str(uuid.uuid4()),
                result.rule_code,
                trigger_type,
                trigger_event,
                target_instance_uid,
                json.dumps({'current_value': result.current_value}, ensure_ascii=False),
                json.dumps({'expected_value': result.expected_value, 'actions': result.triggered_actions}, ensure_ascii=False),
                result.status.value,
                result.message,
                result.execution_time_ms
            ))
            self.db.commit()
            cursor.close()

        except Exception as e:
            logger.error(f"记录执行日志失败: {e}")

    def create_alert(
        self,
        result: RuleExecutionResult,
        target_instance_uid: str = None,
        alert_type: str = 'rule'
    ):
        """创建财务预警"""
        if not self.db or result.status not in [RuleResult.FAIL, RuleResult.WARNING]:
            return

        try:
            cursor = self.db.cursor()

            # 确定严重程度
            severity = 'warning'
            if result.status == RuleResult.FAIL:
                if result.rule_code in self.redline_cache:
                    severity = self.redline_cache[result.rule_code].get('severity', 'warning')
                else:
                    severity = 'error'

            sql = """
                INSERT INTO finance_alerts
                (alert_uid, redline_code, rule_code, alert_type, severity,
                 target_instance_uid, alert_title, alert_message,
                 current_value, expected_value, trace_info)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                str(uuid.uuid4()),
                result.rule_code if alert_type == 'redline' else None,
                result.rule_code if alert_type == 'rule' else None,
                alert_type,
                severity,
                target_instance_uid,
                f"触发规则: {result.rule_code}",
                result.message,
                str(result.current_value),
                str(result.expected_value),
                json.dumps(result.triggered_actions, ensure_ascii=False)
            ))
            self.db.commit()
            cursor.close()

            logger.info(f"创建预警: {result.rule_code} -> {result.message}")

        except Exception as e:
            logger.error(f"创建预警失败: {e}")

# ============================================================================
# 财务域监管引擎
# ============================================================================

class FinanceSupervisionEngine:
    """财务域穿透式监管引擎"""

    def __init__(self, db_connection=None):
        self.db = db_connection
        self.function_engine = MechanismFunctionEngine(db_connection)
        self.rule_engine = BusinessRuleEngine(db_connection)

        # 加载规则
        if db_connection:
            self.rule_engine.load_rules_from_db()
            self.rule_engine.load_redlines_from_db()

    def validate_settlement(
        self,
        settlement_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """验证结算单据"""
        results = {
            'settlement_uid': settlement_data.get('settlement_uid'),
            'validation_status': 'pending',
            'redline_checks': [],
            'rule_checks': [],
            'warnings': [],
            'errors': []
        }

        # 检查合同金额红线
        contract_amount = settlement_data.get('contract_amount')
        if contract_amount:
            check_result = self.rule_engine.check_redline('FR001', contract_amount)
            results['redline_checks'].append({
                'code': 'FR001',
                'name': '合同金额超300万审计红线',
                'status': check_result.status.value,
                'message': check_result.message
            })
            if check_result.status in [RuleResult.FAIL, RuleResult.WARNING]:
                results['warnings'].append(check_result.message)
                self.rule_engine.create_alert(check_result, settlement_data.get('settlement_uid'), 'redline')

        # 检查单笔付款红线
        payment_amount = settlement_data.get('payment_amount')
        if payment_amount:
            check_result = self.rule_engine.check_redline('FR002', payment_amount)
            results['redline_checks'].append({
                'code': 'FR002',
                'name': '单笔付款超100万审批红线',
                'status': check_result.status.value,
                'message': check_result.message
            })
            if check_result.status in [RuleResult.FAIL, RuleResult.WARNING]:
                results['warnings'].append(check_result.message)

        # 检查项目超预算
        budget = settlement_data.get('project_budget')
        actual_cost = settlement_data.get('actual_cost')
        if budget and actual_cost and budget > 0:
            over_budget_rate = (actual_cost - budget) / budget
            check_result = self.rule_engine.check_redline('FR003', over_budget_rate)
            results['redline_checks'].append({
                'code': 'FR003',
                'name': '项目超预算10%预警',
                'status': check_result.status.value,
                'message': check_result.message,
                'current_rate': f"{over_budget_rate * 100:.2f}%"
            })
            if check_result.status in [RuleResult.FAIL, RuleResult.WARNING]:
                results['warnings'].append(check_result.message)

        # 确定最终状态
        if results['errors']:
            results['validation_status'] = 'error'
        elif results['warnings']:
            results['validation_status'] = 'warning'
        else:
            results['validation_status'] = 'validated'

        return results

    def calculate_depreciation(
        self,
        asset_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """计算资产折旧"""
        original_value = asset_data.get('original_value', 0)
        salvage_value = asset_data.get('salvage_value', 0)
        useful_life = asset_data.get('useful_life', 10)

        result = self.function_engine.execute_formula('DEPRECIATION', {
            'original_value': original_value,
            'salvage_value': salvage_value,
            'useful_life': useful_life
        })

        return {
            'asset_uid': asset_data.get('asset_uid'),
            'original_value': original_value,
            'salvage_value': salvage_value,
            'useful_life': useful_life,
            'annual_depreciation': result.result if result.success else 0,
            'monthly_depreciation': result.result / 12 if result.success else 0,
            'calculation_status': 'success' if result.success else 'error',
            'message': result.message
        }

    def analyze_power_loss(
        self,
        line_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """分析线路损耗"""
        current = line_data.get('current', 0)
        resistance = line_data.get('resistance', 0)
        total_power = line_data.get('total_power', 0)

        # 计算线损
        loss_result = self.function_engine.execute_formula('LINE_LOSS', {
            'current': current,
            'resistance': resistance
        })

        # 计算线损率
        rate_result = None
        if loss_result.success and total_power > 0:
            rate_result = self.function_engine.execute_formula('LINE_LOSS_RATE', {
                'loss': loss_result.result,
                'total_power': total_power
            })

        return {
            'line_uid': line_data.get('line_uid'),
            'current': current,
            'resistance': resistance,
            'total_power': total_power,
            'power_loss': loss_result.result if loss_result.success else 0,
            'loss_rate': rate_result.result if rate_result and rate_result.success else 0,
            'analysis_status': 'success' if loss_result.success else 'error',
            'message': loss_result.message
        }

# ============================================================================
# 主入口
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description='机理函数引擎')
    parser.add_argument('--action', choices=['list', 'execute', 'check'],
                       default='list', help='执行动作')
    parser.add_argument('--formula', type=str, help='公式代码')
    parser.add_argument('--redline', type=str, help='红线代码')
    parser.add_argument('--value', type=float, help='检查值')
    parser.add_argument('--params', type=str, help='参数JSON')

    args = parser.parse_args()

    # 初始化引擎
    engine = MechanismFunctionEngine()

    if args.action == 'list':
        print("\n=== 内置物理公式列表 ===\n")
        for formula in engine.get_formula_list():
            print(f"代码: {formula['code']}")
            print(f"描述: {formula['description']}")
            print(f"输入: {formula['inputs']}")
            print(f"输出: {formula['outputs']}")
            print("-" * 40)

    elif args.action == 'execute':
        if not args.formula:
            print("请指定公式代码 --formula")
            return

        params = {}
        if args.params:
            params = json.loads(args.params)

        result = engine.execute_formula(args.formula, params)
        print(f"\n执行结果:")
        print(f"  成功: {result.success}")
        print(f"  结果: {result.result}")
        print(f"  消息: {result.message}")
        print(f"  耗时: {result.execution_time_ms}ms")

    elif args.action == 'check':
        if not args.redline or args.value is None:
            print("请指定红线代码 --redline 和检查值 --value")
            return

        rule_engine = BusinessRuleEngine()
        # 手动添加测试红线
        rule_engine.redline_cache['FR001'] = {
            'redline_code': 'FR001',
            'redline_name': '合同金额超300万审计红线',
            'threshold_value': 3000000,
            'comparison_operator': 'gt',
            'severity': 'warning',
            'trigger_action': '{"action_type": "require_approval"}'
        }

        result = rule_engine.check_redline(args.redline, args.value)
        print(f"\n红线检查结果:")
        print(f"  状态: {result.status.value}")
        print(f"  消息: {result.message}")
        print(f"  当前值: {result.current_value}")
        print(f"  阈值: {result.expected_value}")

if __name__ == '__main__':
    main()
