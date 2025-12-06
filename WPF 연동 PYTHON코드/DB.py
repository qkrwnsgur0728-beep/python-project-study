import sqlite3
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import cv2
import os

# ==========================================
# [0] 설정 (뷰어 전용 기준값)
# ==========================================
# DB 파일 경로 (config.py가 없어도 독립적으로 실행되도록 직접 지정)
DB_PATH = "factory.db"

# 정답 템플릿 (검사할 때 썼던 것과 동일해야 함)
TEMPLATE_X_IDEAL = np.array([  0,  55,  55,   0, -55, -55 ])
TEMPLATE_Y_IDEAL = np.array([ 63,  33, -33, -63, -33,  33 ])

# 공차 기준 (화면 표시용)
TOL_SHAPE = 5.0
TOL_HOLE = 5.0
LIMIT_WARN = 4.5
LIMIT_FAIL = 6.0

# ==========================================
# [1] 데이터 로드 및 파싱 함수
# ==========================================
def get_inspection_data(measure_id):
    if not os.path.exists(DB_PATH):
        print(f"❌ 오류: DB 파일을 찾을 수 없습니다.\n   경로: {DB_PATH}")
        return None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row # 컬럼명으로 데이터 찾기 기능
    cursor = conn.cursor()

    # Measurements 테이블 조회
    try:
        cursor.execute("SELECT * FROM Measurements WHERE measure_id = ?", (measure_id,))
        row = cursor.fetchone()
    except sqlite3.OperationalError:
        print("❌ 오류: 'Measurements' 테이블을 찾을 수 없습니다. DB 파일을 확인하세요.")
        conn.close()
        return None
        
    conn.close()

    if not row:
        print(f"❌ ID {measure_id}번 데이터가 존재하지 않습니다.")
        return None

    print(f"✅ ID {measure_id} 데이터 로드 성공! (결과: {row['inspection_result']})")

    # --- JSON 텍스트 -> 파이썬 변수 변환 (Parsing) ---
    try:
        # 1. 외곽선 좌표
        if row['measured_contour']:
            contour_data = json.loads(row['measured_contour'])
            mx = np.array(contour_data['x'])
            my = np.array(contour_data['y'])
        else:
            mx, my = [], []

        # 2. 중심 및 구멍 정보
        if row['measured_center']:
            center_data = json.loads(row['measured_center'])
            
            hole_found = center_data.get('hole_found', False)
            hole_x = np.array(center_data.get('hole_x', [])) if hole_found else []
            hole_y = np.array(center_data.get('hole_y', [])) if hole_found else []
            
            farthest_x = center_data.get('farthest_x', 0)
            farthest_y = center_data.get('farthest_y', 63)
            hole_cx = center_data.get('hole_cx', 0)
            hole_cy = center_data.get('hole_cy', 0)
            body_cx = center_data.get('body_cx', 0)
            body_cy = center_data.get('body_cy', 0)
        else:
            hole_found = False
            hole_x, hole_y = [], []
            farthest_x, farthest_y = 0, 63
            hole_cx, hole_cy = 0, 0
            body_cx, body_cy = 0, 0

        # 3. AI 데이터 (컬럼이 있을 경우에만)
        keys = row.keys()
        rust_top = json.loads(row['rust_data_top']) if 'rust_data_top' in keys and row['rust_data_top'] else {}
        rust_bot = json.loads(row['rust_data_bottom']) if 'rust_data_bottom' in keys and row['rust_data_bottom'] else {}

        # 4. 기타 정보
        return {
            "mx": mx, "my": my,
            "tx": TEMPLATE_X_IDEAL, "ty": TEMPLATE_Y_IDEAL,
            "fx": farthest_x, "fy": farthest_y,
            "hole_found": hole_found,
            "hx": hole_x, "hy": hole_y,
            "hcx": hole_cx, "hcy": hole_cy,
            "body_cx": body_cx, "body_cy": body_cy,
            "offset": row['hole_offset'] if row['hole_offset'] is not None else 0.0,
            "area": row['area_size'] if row['area_size'] is not None else 0.0,
            "result": row['fail_reason'],
            "time": row['measured_at'],
            "rust_top": rust_top,
            "rust_bot": rust_bot,
            "cam1_path": row['cam1_path'],
            "cam2_path": row['cam2_path']
        }

    except Exception as e:
        print(f"❌ 데이터 파싱 중 오류 발생: {e}")
        return None

# ==========================================
# [2] 헬퍼 함수: 각도 기준 정렬
# ==========================================
def sort_by_angle(x_arr, y_arr):
    if len(x_arr) == 0: return [], [], []
    angles = np.degrees(np.arctan2(y_arr, x_arr))
    angles_clock = (90 - angles) % 360
    sorted_indices = np.argsort(angles_clock)
    return x_arr[sorted_indices], y_arr[sorted_indices], angles_clock[sorted_indices]

# ==========================================
# [3] 시각화 실행 함수
# ==========================================
def show_viewer(measure_id):
    data = get_inspection_data(measure_id)
    if not data: return

    # 변수 할당
    mx, my = data['mx'], data['my']
    tx, ty = data['tx'], data['ty']
    fx, fy = data['fx'], data['fy']
    hx, hy = data['hx'], data['hy']
    
    status_color = 'blue'
    if "OK" in str(data['result']): status_color = 'green'
    if "WARNING" in str(data['result']): status_color = 'orange'
    if "NG" in str(data['result']): status_color = 'red'

    # 화면 구성 (2행 3열) -> 사진 2장 + 그래프 3개 (편차,형상,동심도)
    fig = plt.figure(figsize=(16, 9))
    fig.suptitle(f"Inspection Report [ID: {measure_id}] - {data['time']}", fontsize=16)
    
    # --- [1] Top 이미지 ---
    ax_img1 = plt.subplot2grid((2, 3), (0, 0))
    if data['cam1_path'] and os.path.exists(data['cam1_path']):
        img = cv2.imread(data['cam1_path'])
        if img is not None:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            ax_img1.imshow(img)
            ax_img1.set_title(f"Top Image (Processed)\n{data['result']}", color=status_color, fontweight='bold')
        else:
            ax_img1.text(0.5, 0.5, "Load Failed", ha='center')
    else:
        ax_img1.text(0.5, 0.5, "No Image File", ha='center')
    ax_img1.axis('off')

    # --- [2] Bottom 이미지 ---
    ax_img2 = plt.subplot2grid((2, 3), (1, 0))
    if data['cam2_path'] and os.path.exists(data['cam2_path']):
        img = cv2.imread(data['cam2_path'])
        if img is not None:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            ax_img2.imshow(img)
            ax_img2.set_title("Bottom Image (Processed)")
        else:
            ax_img2.text(0.5, 0.5, "Load Failed", ha='center')
    else:
        ax_img2.text(0.5, 0.5, "No Image File", ha='center')
    ax_img2.axis('off')

    # --- [3] 형상 그래프 (Shape) ---
    ax3 = plt.subplot2grid((2, 3), (0, 1))
    limit = 150
    tx_c = np.append(tx, tx[0]); ty_c = np.append(ty, ty[0])
    
    ax3.plot(tx_c, ty_c, color='lightgreen', linewidth=LIMIT_FAIL*2, alpha=0.4, label='Tolerance')
    ax3.plot(tx_c, ty_c, 'o--', color='grey', label='Ideal')
    
    if len(mx) > 0:
        mx_c = np.append(mx, mx[0]); my_c = np.append(my, my[0])
        ax3.plot(mx_c, my_c, 'b-', linewidth=2, label='Measured')
        
    ax3.plot(0, 0, 'bo', label='Center')
    ax3.plot([0, fx], [0, fy], 'r-', label='Ref Edge')

    ax3.set_xlim(-limit, limit); ax3.set_ylim(-limit, limit)
    ax3.set_aspect('equal'); ax3.grid(True, linestyle=':')
    ax3.legend(loc='upper right', fontsize='small')
    ax3.set_title(f"Shape Analysis")

    # --- [4] 편차 그래프 (Deviation) ---
    ax4 = plt.subplot2grid((2, 3), (1, 1))
    if len(mx) > 0:
        template_pts_cv2 = np.column_stack((tx, -ty)).astype(np.float32)
        devs = []
        mx_s, my_s, angs_s = sort_by_angle(mx, my)
        
        for i in range(len(mx_s)):
            pt = (float(mx_s[i]), float(-my_s[i]))
            dist = cv2.pointPolygonTest(template_pts_cv2, pt, True)
            devs.append(-dist) 

        ax4.plot(angs_s, devs, 'b-', linewidth=1.5)
        
        x_bg = [0, 360]
        ax4.fill_between(x_bg, -LIMIT_WARN, LIMIT_WARN, color='green', alpha=0.15, label='Safe')
        ax4.fill_between(x_bg, LIMIT_WARN, LIMIT_FAIL, color='yellow', alpha=0.2, label='Warn')
        ax4.fill_between(x_bg, -LIMIT_FAIL, -LIMIT_WARN, color='yellow', alpha=0.2)
        ax4.hlines([LIMIT_FAIL, -LIMIT_FAIL], 0, 360, colors='red', linestyles='--')

        for i, d in enumerate(devs):
            if abs(d) > LIMIT_FAIL: ax4.plot(angs_s[i], d, 'ro', markersize=3)
            elif abs(d) > LIMIT_WARN: ax4.plot(angs_s[i], d, 'o', color='orange', markersize=3)

    ax4.set_xlim(0, 360*1.3)
    ax4.set_xticks([0, 60, 120, 180, 240, 300, 360])
    ax4.set_xticklabels(["P0", "P1", "P2", "P3", "P4", "P5", "P0"])
    ax4.grid(True, alpha=0.5)
    ax4.set_title("Deviation Profile")
    ax4.legend(loc='upper right', fontsize='small')

    # --- [5] 동심도 그래프 (Concentricity) ---
    ax5 = plt.subplot2grid((2, 3), (0, 2), rowspan=2)
    zoom = TOL_HOLE * 4
    ax5.add_patch(Circle((0,0), TOL_HOLE, color='green', alpha=0.15, label='Safe Zone'))
    ax5.add_patch(Circle((0,0), TOL_HOLE, color='green', fill=False, linestyle='--'))
    ax5.plot(0, 0, 'k+', markersize=15, label='Body Center')

    if data['hole_found']:
        off = data['offset']
        col = 'blue' if off <= TOL_HOLE else 'red'
        ax5.plot(data['hcx'], data['hcy'], 'o', color=col, label='Hole Center')
        ax5.plot([0, data['hcx']], [0, data['hcy']], color=col, linestyle='-', label=f'Offset: {off:.2f}px')
    else:
        ax5.text(0,0, "NO HOLE", color='red', ha='center')

    ax5.set_xlim(-zoom, zoom); ax5.set_ylim(-zoom, zoom)
    ax5.set_aspect('equal'); ax5.grid(True, linestyle=':')
    ax5.legend(loc='upper right', fontsize='small')
    ax5.set_title(f"Concentricity\nOffset: {data['offset']:.2f}px")

    plt.tight_layout()
    plt.show()

# ==========================================
# [4] 메인 실행 루프
# ==========================================
if __name__ == "__main__":
    while True:
        if not os.path.exists(DB_PATH):
             print(f"❌ 오류: '{DB_PATH}' 파일이 없습니다.")
             break

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        print("\n" + "="*60)
        print(" [ 최근 검사 기록 (Measurements) ]")
        print(f" {'ID':<5} | {'Time':<20} | {'Result':<10} | {'Fail Reason'}")
        print("-" * 60)
        
        try:
            cursor.execute("SELECT measure_id, measured_at, inspection_result, fail_reason FROM Measurements ORDER BY measure_id DESC LIMIT 5")
            rows = cursor.fetchall()
            if not rows:
                print(" (데이터가 없습니다)")
            for r in rows:
                res = r[2] if r[2] else "-"
                reason = r[3] if r[3] else "-"
                print(f" {r[0]:<5} | {r[1]:<20} | {res:<10} | {reason}")
        except sqlite3.OperationalError:
            print(" ❌ 테이블을 찾을 수 없습니다. (DB 파일 또는 테이블명 확인)")

        print("="*60)
        conn.close()

        user_input = input("\n👉 보고 싶은 ID 입력 (q:종료): ")
        
        if user_input.lower() == 'q':
            break
        
        if user_input.isdigit():
            show_viewer(int(user_input))
        else:
            print("❌ 숫자를 입력하세요.")