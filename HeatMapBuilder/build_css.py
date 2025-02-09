import os
import subprocess
import platform
import requests
import sys
from pathlib import Path

def download_tailwind_cli():
    """Download the Tailwind CLI executable"""
    print("Tailwind CLI 다운로드 시작...")
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    # Determine the correct URL based on system and architecture
    if system == "windows":
        url = "https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-windows-x64.exe"
        filename = "tailwindcss.exe"
    elif system == "darwin":
        if "arm" in machine:
            url = "https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-macos-arm64"
        else:
            url = "https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-macos-x64"
        filename = "tailwindcss"
    else:  # Linux
        if "arm" in machine:
            url = "https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-arm64"
        else:
            url = "https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64"
        filename = "tailwindcss"

    print(f"시스템: {system}, 아키텍처: {machine}")
    print(f"다운로드 URL: {url}")
    
    try:
        # Download the file
        print("파일 다운로드 중...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        cli_path = Path(__file__).parent / filename
        print(f"CLI 저장 경로: {cli_path}")
        
        with open(cli_path, 'wb') as f:
            f.write(response.content)
        
        # Make the file executable on Unix-like systems
        if system != "windows":
            os.chmod(cli_path, 0o755)
        else:
            # Windows에서 실행 권한 확인
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                subprocess.run(
                    [str(cli_path), '--help'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    encoding='utf-8',
                    startupinfo=startupinfo
                )
                print("CLI 실행 권한 확인 완료")
            except Exception as e:
                print(f"CLI 실행 권한 확인 실패: {e}", file=sys.stderr)
        
        print("Tailwind CLI 다운로드 완료")
        return cli_path
    except requests.exceptions.RequestException as e:
        print(f"다운로드 실패: {e}", file=sys.stderr)
        raise

def verify_paths(input_css, output_css, config_path):
    """경로 검증 및 파일 내용 확인"""
    print("\n=== 경로 검증 시작 ===")
    
    def check_file(path, name):
        print(f"\n{name} 확인:")
        print(f"경로: {path}")
        print(f"존재여부: {path.exists()}")
        if path.exists():
            print(f"파일크기: {path.stat().st_size:,} bytes")
            if path.suffix in ['.css', '.js']:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        print(f"파일 내용 미리보기 (처음 100자):")
                        print(content[:100])
                except Exception as e:
                    print(f"파일 읽기 실패: {e}")
    
    check_file(input_css, "입력 CSS 파일")
    check_file(output_css.parent, "출력 디렉토리")
    check_file(config_path, "설정 파일")
    
    print("\n=== 경로 검증 완료 ===\n")

def build_css():
    """Build the CSS file using Tailwind CLI"""
    try:
        print("\n=== CSS 빌드 시작 ===")
        
        # Ensure the output directory exists
        output_dir = Path(__file__).parent / "apps" / "webapps" / "static" / "css"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Paths
        input_css = output_dir / "tailwind.css"
        output_css = output_dir / "main.css"
        config_path = Path(__file__).parent / "tailwind.config.js"
        
        # Verify all paths and files
        verify_paths(input_css, output_css, config_path)
        
        # Download Tailwind CLI if not exists
        cli_path = Path(__file__).parent / ("tailwindcss.exe" if platform.system().lower() == "windows" else "tailwindcss")
        if not cli_path.exists():
            print("\nTailwind CLI가 없습니다. 다운로드를 시작합니다...")
            cli_path = download_tailwind_cli()
        
        # Build command
        cmd = [
            str(cli_path),
            "-i", str(input_css),
            "-o", str(output_css),
            "--config", str(config_path),
            "-w",
            "--cwd", str(Path(__file__).parent)
            # "--minify"
        ]
        
        print(f"\n실행할 명령어: {' '.join(cmd)}")
        
        # Windows에서 콘솔 창 숨기기
        startupinfo = None
        if platform.system().lower() == "windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        # Run the build with timeout
        print("\nCSS 빌드 실행 중...")
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=3000,  # 3000초 타임아웃 설정
            encoding='utf-8',  # UTF-8 인코딩 사용
            startupinfo=startupinfo  # Windows에서 콘솔 창 숨기기

        )
        
        if result.stdout:
            print("\n빌드 출력:")
            print(result.stdout)
        
        if result.stderr:
            print("\n빌드 경고/에러:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
        
        if output_css.exists():
            print(f"\nCSS 빌드 완료: {output_css}")
            print(f"파일 크기: {output_css.stat().st_size:,} bytes")
            
            # 빌드된 파일 내용 확인
            try:
                with open(output_css, 'r', encoding='utf-8') as f:
                    content = f.read()
                    print("\n빌드된 CSS 파일 미리보기 (처음 100자):")
                    print(content[:100])
            except Exception as e:
                print(f"\n빌드된 파일 읽기 실패: {e}", file=sys.stderr)
        else:
            raise FileNotFoundError(f"빌드된 CSS 파일이 생성되지 않았습니다: {output_css}")
            
    except subprocess.TimeoutExpired:
        print("\nCSS 빌드 시간 초과 (3000초)", file=sys.stderr)
        raise
    except subprocess.CalledProcessError as e:
        print(f"\nCSS 빌드 실패: {e}", file=sys.stderr)

        print("표준 출력:", e.stdout)
        print("표준 에러:", e.stderr)
        raise
    except Exception as e:
        print(f"\n예상치 못한 오류 발생: {e}", file=sys.stderr)
        raise
    finally:
        print("\n=== CSS 빌드 종료 ===")

if __name__ == "__main__":
    try:
        build_css()
    except Exception as e:
        print(f"\n프로그램 실행 실패: {e}", file=sys.stderr)
        sys.exit(1) 