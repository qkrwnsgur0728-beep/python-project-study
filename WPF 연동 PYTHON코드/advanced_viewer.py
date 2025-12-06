import sqlite3
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import os
import sys

# ==========================================
# [0] 설정 (기존 파일과 독립적인 설정)
# ==========================================
# factory.db 파일이 있는 경로를 자동으로 찾습니다.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "factory.db")

# 만약 data 폴더 안에 있다면 아래 주석 해제
# DB_PATH = os.path.join(BASE_DIR, "data", "factory.db")

# ==========================================
# [1] 데이터 로드 함수
# ==========================================
def get_detail_data(measure_id):
    if not os.path.exists(DB_PATH):
        print(f"❌ [Error] DB 파일을 찾을 수 없습니다: {DB_PATH}")
        return None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
    SELECT m.measure_id, m.measured_contour, m.inspection_result, m.fail_reason, m.measured_center,
           p.tol_shape, p.limit_warn, p.limit_fail, p.tol_hole
    FROM Measurements m
    LEFT JOIN Product p ON m.product_id = p.product_id
    WHERE m.measure_id = ?
    """
    
    try:
        cursor.execute(query, (measure_id,))
        row = cursor.fetchone()
    except Exception as e:
        print(f"❌ 쿼리 실행 오류: {e}")
        conn.close()
        return None
        
    conn.close()

    if not row:
        print(f"❌ ID {measure_id}번 데이터가 존재하지 않습니다.")
        return None

    # 데이터 파싱
    try:
        contour = json.loads(row['measured_contour']) if row['measured_contour'] else {'x': [], 'y': []}
        center_info = json.loads(row['measured_center']) if row['measured_center'] else {}
        
        return {
            "id": row['measure_id'],
            "result": row['inspection_result'],
            "reason": row['fail_reason'],
            "x": np.array(contour.get('x', [])),
            "y": np.array(contour.get('y', [])),
            "hole_found": center_info.get('hole_found', False),
            "hole_cx": center_info.get('hole_cx', 0),
            "hole_cy": center_info.get('hole_cy', 0),
            "body_cx": center_info.get('body_cx', 0), # 픽셀 좌표일 수 있음
            "tol_shape": row['tol_shape'] if row['tol_shape'] else 5.0,
            "limit_warn": row['limit_warn'] if row['limit_warn'] else 4.5,
            "limit_fail": row['limit_fail'] if row['limit_fail'] else 6.0,
            "tol_hole": row['tol_hole'] if row['tol_hole'] else 5.0
        }
    except Exception as e:
        print(f"❌ 데이터 파싱 오류: {e}")
        return None

# ==========================================
# [2] 상세 시각화 함수 (3분할 차트)
# ==========================================
def show_advanced_dashboard(measure_id):
    data = get_detail_data(measure_id)
    if not data: return

    # 그래프 설정 (1행 3열)
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    result_color = 'green' if 'OK' in data['result'] else 'red'
    plt.suptitle(f"Advanced Inspection Analysis [ID: {data['id']}] - {data['result']}", 
                 fontsize=16, color=result_color, fontweight='bold')

    # -------------------------------------------------------
    # [차트 1] Shape Analysis (형상 분석)
    # -------------------------------------------------------
    ax1 = axes[0]
    ax1.set_title("1. Shape Analysis", fontsize=12, fontweight='bold')
    
    if len(data['x']) > 0:
        # 외곽선
        ax1.plot(data['x'], data['y'], 'b-', linewidth=2, label='Measured')
        ax1.fill(data['x'], data['y'], 'blue', alpha=0.05)
        
        # 중심점 (0,0 기준)
        ax1.scatter(0, 0, c='red', marker='+', s=150, label='Ref Center')
        
        # 공차 영역 표시 (가상)
        ax1.plot(data['x'], data['y'] + data['tol_shape'], 'g--', alpha=0.3)
        ax1.plot(data['x'], data['y'] - data['tol_shape'], 'g--', alpha=0.3)
    else:
        ax1.text(0, 0, "No Contour Data", ha='center')

    ax1.grid(True, linestyle=':')
    ax1.legend(loc='upper right')
    ax1.set_aspect('equal')

    # -------------------------------------------------------
    # [차트 2] Deviation Profile (형상 오차 그래프)
    # -------------------------------------------------------
    ax2 = axes[1]
    ax2.set_title("2. Deviation Profile", fontsize=12, fontweight='bold')

    if len(data['x']) > 0:
        # 간단한 오차 계산 (중심으로부터의 거리 변동성)
        # 실제로는 Ideal Template과의 거리를 써야 하지만, 여기서는 평균 반경 대비 차이로 근사 시각화
        radii = np.sqrt(data['x']**2 + data['y']**2)
        mean_radius = np.mean(radii)
        deviations = radii - mean_radius 

        # 배경 색상 (Safe / Warn / Fail)
        ax2.axhspan(-data['limit_warn'], data['limit_warn'], color='green', alpha=0.1, label='Safe')
        ax2.axhspan(data['limit_warn'], data['limit_fail'], color='yellow', alpha=0.2, label='Warn')
        ax2.axhspan(-data['limit_fail'], -data['limit_warn'], color='yellow', alpha=0.2)
        
        # 한계선
        ax2.axhline(data['limit_fail'], color='red', linestyle='--', label='Fail Limit')
        ax2.axhline(-data['limit_fail'], color='red', linestyle='--')

        # 데이터 플롯
        ax2.plot(deviations, 'b.-', linewidth=1, markersize=3)
        ax2.set_ylim(-data['limit_fail'] * 2, data['limit_fail'] * 2)
    else:
        ax2.text(0.5, 0.5, "No Data", ha='center')

    ax2.grid(True, alpha=0.5)
    ax2.set_xlabel("Points")
    ax2.set_ylabel("Deviation (px)")
    ax2.legend(loc='upper right', fontsize='small')

    # -------------------------------------------------------
    # [차트 3] Concentricity (동심도/구멍 위치)
    # -------------------------------------------------------
    ax3 = axes[2]
    offset_val = np.sqrt(data['hole_cx']**2 + data['hole_cy']**2)
    ax3.set_title(f"3. Concentricity\nOffset: {offset_val:.2f} px", fontsize=12, fontweight='bold')

    # 안전 구역 (녹색 원)
    safe_radius = data['tol_hole']
    ax3.add_patch(Circle((0, 0), radius=safe_radius, color='green', alpha=0.15))
    ax3.add_patch(Circle((0, 0), radius=safe_radius, color='green', fill=False, linestyle='--', label='Tolerance'))

    # 중심점들
    ax3.scatter(0, 0, c='black', marker='+', s=200, label='Body Center') # 기준
    
    if data['hole_found']:
        # 구멍 위치
        col = 'blue' if offset_val <= safe_radius else 'red'
        ax3.scatter(data['hole_cx'], data['hole_cy'], c=col, marker='o', s=80, label='Hole Center')
        # 연결선
        ax3.plot([0, data['hole_cx']], [0, data['hole_cy']], color=col, linestyle='-')
    else:
        ax3.text(0, 0, "Hole Not Found", ha='center', color='red')

    limit_zoom = safe_radius * 3
    ax3.set_xlim(-limit_zoom, limit_zoom)
    ax3.set_ylim(-limit_zoom, limit_zoom)
    ax3.grid(True, linestyle=':')
    ax3.set_aspect('equal')
    ax3.legend(loc='upper right', fontsize='small')

    plt.tight_layout()
    plt.show()

# ==========================================
# [3] 메인 실행부
# ==========================================
if __name__ == "__main__":
    print("\n📊 [고급 분석 뷰어] 실행 중...")
    print(f"📂 연결된 DB: {DB_PATH}")
    
    while True:
        try:
            val = input("\n👉 분석할 Measure ID를 입력하세요 (q: 종료): ")
            if val.lower() == 'q':
                print("종료합니다.")
                break
            
            mid = int(val)
            show_advanced_dashboard(mid)
            
        except ValueError:
            print("❌ 숫자를 입력해주세요.")
        except Exception as e:
            print(f"❌ 오류 발생: {e}")