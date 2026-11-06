"""
실행 프로그램 (GUI) — 담당: 김진웅

실행: python app/gui.py  (또는 맨 위 폴더의 run.bat)
기능
    1. 파일 또는 폴더 선택 → 처리 대상 파일이 바로 목록에 표시 (폴더는 하위 폴더 포함)
    2. 목록에서 처리할 파일만 체크 (전체 선택 / 전체 해제)
    3. 처리 방식 선택(마스킹 / 점검만) → 실행 → 체크한 파일만 처리
    4. 파일을 누르면 탐지 위치를 아래에 표시 (원문 대신 가린 문장)
처리는 CLI와 똑같이 pipeline.run_batch()를 사용한다.
"""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont

from pipeline import run_batch, collect_files, ModuleOutputError, DEFAULT_OUT
from fileio.loader import is_supported
from main import TYPE_NAMES, describe_counts

APP_TITLE = "개인정보 자동 탐지·마스킹"
MODES = [("mask", "마스킹 (처리본 생성)"), ("check", "점검만 (파일 안 만듦)")]


# ---------------------------------------------------------------- 체크박스 그림
def _blend(fg, bg, a):
    return tuple(round(f * a + b * (1 - a)) for f, b in zip(fg, bg))


def _dist_to_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def make_checkbox_image(size, checked):
    """Windows 11 스타일 체크박스 그림 (체크: 파란 바탕+흰 체크 / 해제: 회색 테두리 빈 칸)"""
    blue, white, gray = (0, 95, 184), (255, 255, 255), (134, 134, 134)
    img = tk.PhotoImage(width=size, height=size)
    r = size * 0.22                       # 모서리 둥글기
    stroke = max(1.0, size / 16)          # 테두리 두께
    check = [(0.27, 0.52), (0.44, 0.69), (0.75, 0.35)]
    pts = [(x * size, y * size) for x, y in check]
    cw = size * 0.11                      # 체크 선 두께(절반)
    ss = 4                                # 가장자리를 부드럽게 하기 위한 세부 샘플 수

    def inside_round_rect(x, y, inset):
        lo, hi = inset, size - inset
        rr = max(0.0, r - inset)
        cx = min(max(x, lo + rr), hi - rr)
        cy = min(max(y, lo + rr), hi - rr)
        return lo <= x <= hi and lo <= y <= hi and (x - cx) ** 2 + (y - cy) ** 2 <= rr ** 2

    rows = []
    for py in range(size):
        row = []
        for px in range(size):
            cover = inner = mark = 0
            for sy in range(ss):
                for sx in range(ss):
                    x, y = px + (sx + 0.5) / ss, py + (sy + 0.5) / ss
                    if inside_round_rect(x, y, 0.5):
                        cover += 1
                        if inside_round_rect(x, y, 0.5 + stroke):
                            inner += 1
                    if checked and min(_dist_to_segment(x, y, *pts[0], *pts[1]),
                                       _dist_to_segment(x, y, *pts[1], *pts[2])) <= cw:
                        mark += 1
            n = ss * ss
            if cover / n < 0.5:
                row.append(None)          # 바깥: 투명
                continue
            if checked:
                color = _blend(white, blue, mark / n)
            else:
                color = _blend(white, gray, inner / cover)
            row.append("#%02x%02x%02x" % color)
        rows.append(row)

    for py, row in enumerate(rows):
        for px, c in enumerate(row):
            if c is None:
                img.transparency_set(px, py, True)
            else:
                img.put(c, (px, py))
    return img
SUPPORTED_HINT = "docx, txt, log, csv, json, 소스코드 등"


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=12)
        self.root = root
        self.events = queue.Queue()     # 작업 스레드 → 화면 갱신용
        self.rows = {}                  # 목록 행 id(=파일 경로) → {"name", "checked", "result", "error"}
        self.running = False
        self._refresh_job = None

        root.title(APP_TITLE)
        root.minsize(760, 560)
        self.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self.input_var = tk.StringVar()
        self.out_var = tk.StringVar(value=DEFAULT_OUT)
        self.mode_var = tk.StringVar(value="mask")
        self.status_var = tk.StringVar(value="파일이나 폴더를 선택하세요.")
        self.count_var = tk.StringVar(value="")

        # 글자 크기에 맞춰 체크박스 크기 결정 (고해상도 화면 대응)
        line = tkfont.nametofont("TkDefaultFont").metrics("linespace")
        box = max(13, min(28, round(line * 0.9)))
        self.img_on = make_checkbox_image(box, True)
        self.img_off = make_checkbox_image(box, False)
        ttk.Style().configure("Treeview", rowheight=max(line + 6, box + 8))

        self._build()
        # 입력·저장 위치가 바뀌면 목록을 바로 다시 만들고, 처리 방식이 바뀌면 이전 결과만 지움
        self.input_var.trace_add("write", self._schedule_refresh)
        self.out_var.trace_add("write", self._schedule_refresh)
        self.mode_var.trace_add("write", lambda *_: self._reset_results("처리 방식이 바뀌었습니다. [실행]을 눌러주세요."))
        self.after(100, self._poll)

    # ------------------------------------------------------------ 화면 구성
    def _build(self):
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="입력").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(self, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", padx=6)
        btns = ttk.Frame(self)
        btns.grid(row=0, column=2, sticky="e")
        ttk.Button(btns, text="파일 선택", command=self.pick_file).pack(side="left")
        ttk.Button(btns, text="폴더 선택", command=self.pick_folder).pack(side="left", padx=(4, 0))

        ttk.Label(self, text="저장 폴더").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(self, textvariable=self.out_var).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(self, text="찾아보기", command=self.pick_out).grid(row=1, column=2, sticky="e")

        mode_box = ttk.LabelFrame(self, text="처리 방식", padding=(8, 4))
        mode_box.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        for value, label in MODES:
            ttk.Radiobutton(mode_box, text=label, value=value, variable=self.mode_var).pack(side="left", padx=(0, 16))

        # 목록 위 도구줄: 전체 선택/해제 + 선택 개수
        list_bar = ttk.Frame(self)
        list_bar.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(6, 2))
        ttk.Label(list_bar, text="처리 대상").pack(side="left")
        ttk.Button(list_bar, text="전체 선택", command=lambda: self.set_all(True)).pack(side="left", padx=(10, 0))
        ttk.Button(list_bar, text="전체 해제", command=lambda: self.set_all(False)).pack(side="left", padx=(4, 0))
        ttk.Label(list_bar, textvariable=self.count_var).pack(side="right")

        table_box = ttk.Frame(self)
        table_box.grid(row=4, column=0, columnspan=3, sticky="nsew")
        table_box.columnconfigure(0, weight=1)
        table_box.rowconfigure(0, weight=1)
        cols = ("count", "types", "output")
        self.table = ttk.Treeview(table_box, columns=cols, show="tree headings", height=7, selectmode="browse")
        self.table.heading("#0", text="파일 (체크박스 클릭 또는 Space로 선택)")
        self.table.heading("count", text="건수")
        self.table.heading("types", text="종류")
        self.table.heading("output", text="결과")
        self.table.column("#0", width=260)
        self.table.column("count", width=50, anchor="center", stretch=False)
        self.table.column("types", width=300)
        self.table.column("output", width=150)
        self.table.tag_configure("error", foreground="#c0392b")
        self.table.tag_configure("off", foreground="#999999")
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_box, orient="vertical", command=self.table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", self.show_detail)
        self.table.bind("<Button-1>", self._on_click, add=True)
        self.table.bind("<space>", self._on_space)
        self.rowconfigure(4, weight=2)

        run_row = ttk.Frame(self)
        run_row.grid(row=5, column=0, columnspan=3, sticky="ew", pady=6)
        run_row.columnconfigure(1, weight=1)
        self.run_btn = ttk.Button(run_row, text="실행", command=self.start)
        self.run_btn.grid(row=0, column=0)
        self.progress = ttk.Progressbar(run_row, mode="determinate")
        self.progress.grid(row=0, column=1, sticky="ew", padx=8)
        self.open_btn = ttk.Button(run_row, text="결과 폴더 열기", command=self.open_output, state="disabled")
        self.open_btn.grid(row=0, column=2)

        ttk.Label(self, text="상세 (선택한 파일의 탐지 위치 — 원문 대신 가린 문장으로 표시)").grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(4, 2))
        self.detail = tk.Text(self, height=9, wrap="word", state="disabled")
        self.detail.grid(row=7, column=0, columnspan=3, sticky="nsew")
        self.rowconfigure(7, weight=2)

        ttk.Label(self, textvariable=self.status_var).grid(row=8, column=0, columnspan=3, sticky="w", pady=(6, 0))

    # ------------------------------------------------------------ 입력 선택
    def pick_file(self):
        path = filedialog.askopenfilename(title="처리할 파일")
        if path:
            self.input_var.set(os.path.normpath(path))

    def pick_folder(self):
        path = filedialog.askdirectory(title="처리할 폴더")
        if path:
            self.input_var.set(os.path.normpath(path))

    def pick_out(self):
        path = filedialog.askdirectory(title="저장 폴더")
        if path:
            self.out_var.set(os.path.normpath(path))

    # ------------------------------------------------------------ 처리 대상 목록
    def _schedule_refresh(self, *_):
        """입력칸에 직접 타이핑하는 경우를 위해 잠깐 기다렸다가 목록 갱신"""
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
        self._refresh_job = self.after(300, self.refresh_list)

    def refresh_list(self):
        self._refresh_job = None
        if self.running:
            return
        src = self.input_var.get().strip()
        unchecked = {p for p, r in self.rows.items() if not r["checked"]}  # 다시 만들어도 체크 해제한 건 유지
        self.table.delete(*self.table.get_children())
        self.rows.clear()
        self._set_detail("")
        self.progress["value"] = 0
        self.open_btn.configure(state="disabled")

        if not src:
            self._update_count()
            self.status_var.set("파일이나 폴더를 선택하세요.")
            return
        if not os.path.exists(src):
            self._update_count()
            self.status_var.set("입력한 경로를 찾을 수 없습니다.")
            return
        if os.path.isfile(src) and not is_supported(src):
            self._update_count()
            self.status_var.set(f"지원하지 않는 형식입니다. (지원: {SUPPORTED_HINT})")
            return

        try:
            files = collect_files(src, self.out_var.get().strip() or DEFAULT_OUT)
        except Exception as e:
            self._update_count()
            self.status_var.set(f"목록을 만들 수 없습니다: {e}")
            return

        base = src if os.path.isdir(src) else os.path.dirname(src)
        for f in files:
            name = os.path.relpath(f, base)
            self.rows[f] = {"name": name, "checked": f not in unchecked, "result": None, "error": None}
            self.table.insert("", "end", iid=f, text="", values=("", "", ""))
            self._render(f)

        self._update_count()
        if files:
            self.status_var.set("처리할 파일을 확인하고 [실행]을 눌러주세요.")
        else:
            self.status_var.set(f"폴더 안에 지원하는 형식의 파일이 없습니다. (지원: {SUPPORTED_HINT})")

    def _render(self, iid):
        row = self.rows[iid]
        tags = ()
        if row["error"]:
            values = ("-", "실패", row["error"])
            tags = ("error",)
        elif row["result"]:
            r = row["result"]
            out = os.path.basename(r["output_path"]) if r["output_path"] else "점검만"
            values = (r["total"], describe_counts(r["counts"]), out)
        else:
            values = ("", "", "" if row["checked"] else "선택 안 함")
            if not row["checked"]:
                tags = ("off",)
        self.table.item(iid, text=f" {row['name']}", image=self.img_on if row["checked"] else self.img_off,
                        values=values, tags=tags)

    def _update_count(self):
        total = len(self.rows)
        on = sum(r["checked"] for r in self.rows.values())
        self.count_var.set(f"선택 {on} / 전체 {total}개" if total else "")

    def toggle(self, iid):
        if self.running or iid not in self.rows:
            return
        self.rows[iid]["checked"] = not self.rows[iid]["checked"]
        self._render(iid)
        self._update_count()

    def set_all(self, checked):
        if self.running:
            return
        for iid, row in self.rows.items():
            row["checked"] = checked
            self._render(iid)
        self._update_count()

    def _on_click(self, event):
        """파일 이름 앞 체크박스를 클릭하면 선택 전환"""
        if self.table.identify_region(event.x, event.y) != "tree":
            return
        iid = self.table.identify_row(event.y)
        if not iid:
            return
        if self.table.identify_element(event.x, event.y) == "image":
            self.toggle(iid)
            return "break"

    def _on_space(self, _event):
        for iid in self.table.selection():
            self.toggle(iid)
        return "break"

    def _reset_results(self, message=None):
        """목록은 그대로 두고 이전 실행 결과만 지운다."""
        if self.running:
            return
        had_result = any(r["result"] or r["error"] for r in self.rows.values())
        for iid, row in self.rows.items():
            row["result"] = row["error"] = None
            self._render(iid)
        self._set_detail("")
        self.progress["value"] = 0
        self.open_btn.configure(state="disabled")
        if message and had_result:
            self.status_var.set(message)

    # ------------------------------------------------------------ 실행
    def start(self):
        if self.running:
            return
        if self._refresh_job:  # 입력을 막 바꾼 직후라면 목록부터 갱신
            self.after_cancel(self._refresh_job)
            self.refresh_list()
        src = self.input_var.get().strip()
        if not src or not os.path.exists(src):
            messagebox.showwarning(APP_TITLE, "입력 파일이나 폴더를 선택하세요.")
            return
        files = [p for p, r in self.rows.items() if r["checked"]]
        if not files:
            messagebox.showwarning(APP_TITLE, "처리할 파일을 하나 이상 선택하세요.")
            return
        out = self.out_var.get().strip() or DEFAULT_OUT
        mode = self.mode_var.get()

        self._reset_results()
        self.running = True
        self.run_btn.configure(state="disabled")
        self.status_var.set(f"처리 중... 0/{len(files)}")
        threading.Thread(target=self._work, args=(src, files, out, mode), daemon=True).start()

    def _work(self, src, files, out, mode):
        """작업 스레드: 화면은 직접 건드리지 않고 queue로만 알린다."""
        def on_progress(i, n, path, result, error):
            self.events.put(("progress", i, n, path, result, error))

        try:
            summary = run_batch(src, out_dir=out, check_only=(mode == "check"),
                                on_progress=on_progress, files=files)
            self.events.put(("done", summary, mode))
        except ModuleOutputError as e:
            self.events.put(("fail", f"모듈 형식 오류\n\n{e}"))
        except Exception as e:
            self.events.put(("fail", str(e)))

    def _poll(self):
        try:
            while True:
                self._handle(self.events.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _handle(self, ev):
        kind = ev[0]
        if kind == "progress":
            _, i, n, path, result, error = ev
            self.progress.configure(maximum=n, value=i)
            if path in self.rows:
                self.rows[path]["result"], self.rows[path]["error"] = result, error
                self._render(path)
                self.table.see(path)
            self.status_var.set(f"처리 중... {i}/{n}")
        elif kind == "done":
            _, summary, mode = ev
            self._finish(summary, mode)
        elif kind == "fail":
            self.running = False
            self.run_btn.configure(state="normal")
            self.status_var.set("중단됨")
            messagebox.showerror(APP_TITLE, ev[1])

    def _finish(self, summary, mode):
        self.running = False
        self.run_btn.configure(state="normal")
        results, errors = summary["results"], summary["errors"]
        total = {}
        for r in results:
            for t, n in r["counts"].items():
                total[t] = total.get(t, 0) + n
        word = "점검" if mode == "check" else "처리"
        msg = f"{word} 완료: 파일 {len(results)}개, 개인정보 {sum(total.values())}건 ({describe_counts(total)})"
        if errors:
            msg += f" / 실패 {len(errors)}개"
        self.status_var.set(msg)
        if mode != "check" and results:
            self.open_btn.configure(state="normal")
        # 탐지 결과가 있는 첫 파일을 펼쳐 보여줌
        done = [p for p, r in self.rows.items() if r["result"] or r["error"]]
        found = [p for p in done if self.rows[p]["result"] and self.rows[p]["result"]["total"]]
        if found or done:
            first = (found or done)[0]
            self.table.selection_set(first)
            self.table.see(first)

    # ------------------------------------------------------------ 결과 보기
    def show_detail(self, _event=None):
        sel = self.table.selection()
        if not sel or sel[0] not in self.rows:
            return
        path, row = sel[0], self.rows[sel[0]]
        if row["error"]:
            self._set_detail(f"{path}\n\n처리 실패: {row['error']}")
            return
        if not row["result"]:
            state = "아직 처리하지 않았습니다." if row["checked"] else "선택하지 않은 파일입니다."
            self._set_detail(f"{path}\n\n{state}")
            return
        result = row["result"]
        lines = [path]
        if result["output_path"]:
            lines.append(f"→ {result['output_path']}")
        lines.append("")
        if not result["findings"]:
            lines.append("탐지된 개인정보가 없습니다.")
        for f in result["findings"]:
            types = ", ".join(TYPE_NAMES.get(t, t) for t in f["types"])
            lines.append(f"{f['location']}  [{types}]  {f['preview']}")
        self._set_detail("\n".join(lines))

    def _set_detail(self, text):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def open_output(self):
        path = os.path.abspath(self.out_var.get().strip() or DEFAULT_OUT)
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])


def main():
    if sys.platform.startswith("win"):
        try:  # 고해상도 모니터에서 글자 흐림 방지
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
