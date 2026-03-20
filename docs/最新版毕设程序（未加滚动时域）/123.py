import gurobipy as gp
from gurobipy import GRB
import os
import time


def solve_lp_file(lp_file_path, result_dir="lp_results"):
    """
    使用 Gurobi 求解 LP 格式的数学规划模型

    参数:
        lp_file_path: str - LP 文件的路径（绝对路径或相对路径）
        result_dir: str - 结果输出目录（默认自动创建 lp_results 文件夹）
    """
    # 验证 LP 文件是否存在
    if not os.path.exists(lp_file_path):
        raise FileNotFoundError(f"LP 文件不存在：{lp_file_path}")

    # 创建结果输出目录
    os.makedirs(result_dir, exist_ok=True)

    # 1. 初始化 Gurobi 环境（指定日志输出路径，可选）
    env = None
    model = None
    try:
        # env = gp.Env(empty=True)  # 不自动输出日志
        # env.setParam('LogFile', os.path.join(result_dir, 'gurobi.log'))  # 日志保存到文件
        # env.start()
        start1 = time.time()
        # 2. 读取 LP 文件（若不指定 env，使用默认环境）
        model = gp.read(lp_file_path)

        # 3. （可选）设置求解参数（根据需求调整）
        model.Params.TimeLimit = 3600  # 求解时间限制（秒）
        model.Params.MIPGap = 1e-4  # MIP 问题的最优性差距（连续问题无效）
        model.Params.OutputFlag = 1  # 1=输出求解过程，0=静默模式
        model.Params.Presolve = 2  # 强化预处理（加速求解）

        # 4. 求解模型
        print(f"开始求解 LP 文件：{lp_file_path}")
        print(f"求解参数：时间限制={model.Params.TimeLimit}s，最优性差距={model.Params.MIPGap}")
        model.optimize()
        start2 = time.time()

        print("算法时间:",start2-start1)

        # 若找到最优解，输出详细结果
        if status == GRB.OPTIMAL:
            print(f"目标函数值：{model.ObjVal:.6f}")



        # 若模型无解，输出不可行性证明（Farkas 证书）
        elif status == GRB.INFEASIBLE:
            print("生成不可行性证明...")
            model.computeIIS()  # 计算不可行性指标集
            iis_file = os.path.join(result_dir, f"{os.path.basename(lp_file_path)}.iis")
            model.write(iis_file)  # 保存 IIS 到文件
            print(f"不可行性证明已保存到：{iis_file}")

    except gp.GurobiError as e:
        print(f"\nGurobi 错误：代码 {e.errno} - {e.message}")
    except Exception as e:
        print(f"\n未知错误：{str(e)}")
    finally:
        # 释放资源（关键：避免内存泄漏）
        if model is not None:
            model.dispose()
        if env is not None:
            env.dispose()
        print("\n求解结束，资源已释放")


# ------------------- 示例调用 -------------------
if __name__ == "__main__":
    # 替换为你的 LP 文件路径（相对路径或绝对路径）
    LP_FILE = "large_problem.lp"  # 例如："C:/models/my_model.lp" 或 "./models/my_model.lp"

    # 调用求解函数
    solve_lp_file(LP_FILE)