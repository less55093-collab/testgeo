"""
AI Crawler Web UI - Flask Application
"""

import json
import os
import asyncio
import threading
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.crawler import JobManager

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ai-crawler-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state for crawler
crawler_state = {
    'running': False,
    'current_job': None,
    'current_run': None,
    'progress': 0,
    'total': 0,
    'current_keyword': '',
    'success_count': 0,
    'fail_count': 0,
    'logs': []
}

# Job manager instance
job_manager = JobManager()

# Base paths
BASE_DIR = Path(__file__).parent.parent
JOBS_DIR = BASE_DIR / 'jobs'
CONFIG_PATH = BASE_DIR / 'config.json'


# ==================== Pages ====================

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')


@app.route('/jobs')
def jobs_page():
    """Job management page"""
    return render_template('jobs.html')


@app.route('/crawler')
def crawler_page():
    """Crawler control page"""
    return render_template('crawler.html')


@app.route('/report/<job_name>/<run_id>')
def report_page(job_name, run_id):
    """Report viewer page"""
    report_path = JOBS_DIR / job_name / 'runs' / run_id / 'report.html'
    if report_path.exists():
        return send_from_directory(
            str(report_path.parent),
            'report.html'
        )
    return "报告不存在", 404


@app.route('/settings')
def settings_page():
    """Settings page"""
    return render_template('settings.html')


# ==================== Job API ====================

@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List all jobs with their metadata"""
    jobs = []
    if JOBS_DIR.exists():
        for job_dir in JOBS_DIR.iterdir():
            if job_dir.is_dir():
                metadata_path = job_dir / 'metadata.json'
                if metadata_path.exists():
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                        jobs.append({
                            'name': job_dir.name,
                            'keywords_count': len(metadata.get('keywords', [])),
                            'target_product': metadata.get('target_product'),
                            'runs_count': len(metadata.get('runs', [])),
                            'created_at': metadata.get('created_at'),
                            'last_run': metadata['runs'][-1] if metadata.get('runs') else None
                        })
    return jsonify(jobs)


@app.route('/api/jobs', methods=['POST'])
def create_job():
    """Create a new job"""
    data = request.json
    job_name = data.get('name', '').strip()
    keywords = data.get('keywords', [])
    target_product = data.get('target_product', '').strip() or None
    
    if not job_name:
        return jsonify({'error': '任务名称不能为空'}), 400
    if not keywords:
        return jsonify({'error': '关键词不能为空'}), 400
    
    # Check if job exists
    job_path = JOBS_DIR / job_name
    if job_path.exists():
        return jsonify({'error': f'任务 "{job_name}" 已存在'}), 400
    
    try:
        job_manager.create_job(job_name, keywords, target_product)
        return jsonify({'success': True, 'message': f'任务 "{job_name}" 创建成功'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<job_name>', methods=['GET'])
def get_job(job_name):
    """Get job details"""
    metadata_path = JOBS_DIR / job_name / 'metadata.json'
    if not metadata_path.exists():
        return jsonify({'error': '任务不存在'}), 404
    
    with open(metadata_path, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    
    return jsonify(metadata)


@app.route('/api/jobs/<job_name>', methods=['DELETE'])
def delete_job(job_name):
    """Delete a job"""
    import shutil
    job_path = JOBS_DIR / job_name
    if not job_path.exists():
        return jsonify({'error': '任务不存在'}), 404
    
    try:
        shutil.rmtree(job_path)
        return jsonify({'success': True, 'message': f'任务 "{job_name}" 已删除'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== Crawler API ====================

@app.route('/api/crawler/status', methods=['GET'])
def crawler_status():
    """Get current crawler status"""
    return jsonify(crawler_state)


@app.route('/api/crawler/start', methods=['POST'])
def start_crawler():
    """Start crawling a job"""
    global crawler_state
    
    if crawler_state['running']:
        return jsonify({'error': '爬虫正在运行中'}), 400
    
    data = request.json
    job_name = data.get('job_name')
    mode = data.get('mode', 'new')  # 'new', 'resume', 'rerun'
    
    if not job_name:
        return jsonify({'error': '请选择任务'}), 400
    
    # Start crawler in background thread
    thread = threading.Thread(target=run_crawler_async, args=(job_name, mode))
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': '爬虫已启动'})


@app.route('/api/crawler/stop', methods=['POST'])
def stop_crawler():
    """Stop the running crawler"""
    global crawler_state
    
    if not crawler_state['running']:
        return jsonify({'error': '爬虫未在运行'}), 400
    
    crawler_state['running'] = False
    return jsonify({'success': True, 'message': '爬虫已停止'})


def run_crawler_async(job_name, mode):
    """Run crawler in background"""
    global crawler_state
    
    crawler_state['running'] = True
    crawler_state['current_job'] = job_name
    crawler_state['progress'] = 0
    crawler_state['success_count'] = 0
    crawler_state['fail_count'] = 0
    crawler_state['logs'] = []
    
    def log(message):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        crawler_state['logs'].append(log_entry)
        if len(crawler_state['logs']) > 100:
            crawler_state['logs'] = crawler_state['logs'][-100:]
        socketio.emit('log', {'message': log_entry})
    
    def update_progress(current, total, keyword, success, fail):
        crawler_state['progress'] = current
        crawler_state['total'] = total
        crawler_state['current_keyword'] = keyword
        crawler_state['success_count'] = success
        crawler_state['fail_count'] = fail
        socketio.emit('progress', {
            'current': current,
            'total': total,
            'keyword': keyword,
            'success': success,
            'fail': fail,
            'percentage': int((current / total) * 100) if total > 0 else 0
        })
    
    try:
        log(f"开始爬取任务: {job_name}")
        
        # Load job metadata
        metadata = job_manager.load_job(job_name)
        
        # Determine keywords and run
        if mode == 'new' or mode == 'rerun':
            run_id = job_manager.start_run(job_name)
            keywords_to_process = metadata.keywords
        else:  # resume
            if not metadata.runs:
                log("错误: 任务没有运行记录")
                return
            current_run = metadata.runs[-1]
            run_id = current_run['run_id']
            keywords_to_process = job_manager.get_unprocessed_keywords(job_name, run_id)
        
        crawler_state['current_run'] = run_id
        log(f"运行ID: {run_id}")
        log(f"待处理关键词: {len(keywords_to_process)} 个")
        
        # Import provider
        from provider.providers.deepseek import DeepSeek
        from provider.core.types import CallParams
        
        deepseek = DeepSeek(str(CONFIG_PATH))
        
        total = len(keywords_to_process)
        success_count = 0
        fail_count = 0
        
        for i, keyword in enumerate(keywords_to_process):
            if not crawler_state['running']:
                log("爬虫已停止")
                job_manager.update_run_status(job_name, run_id, status='paused')
                break
            
            update_progress(i + 1, total, keyword, success_count, fail_count)
            log(f"正在处理: {keyword}")
            
            try:
                # Create call params
                params = CallParams(
                    messages=[{"role": "user", "content": keyword}],
                    enable_thinking=False,
                    enable_search=True,
                )
                
                # Make API call
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(deepseek.call(params))
                loop.close()
                
                # Save result
                job_manager.save_keyword_result(
                    job_name, run_id, keyword,
                    success=True,
                    content=result.content,
                    rankings=result.rankings,
                    sources=result.sources
                )
                
                success_count += 1
                log(f"✓ 成功: {keyword}")
                
            except Exception as e:
                fail_count += 1
                log(f"✗ 失败: {keyword} - {str(e)}")
                job_manager.save_keyword_result(
                    job_name, run_id, keyword,
                    success=False,
                    error=str(e)
                )
        
        # Update final status
        if crawler_state['running']:
            job_manager.update_run_status(job_name, run_id, status='completed')
            log(f"爬取完成! 成功: {success_count}, 失败: {fail_count}")
            
            # Auto-run analyzer
            log("正在生成分析报告...")
            try:
                from crawler.analyzer import ResultLoader, StatisticsCalculator, ReportGenerator
                
                loader = ResultLoader()
                results = loader.load_run_results(job_name, run_id)
                
                calculator = StatisticsCalculator()
                stats = calculator.calculate(results, metadata.target_product)
                stats.job_name = job_name
                stats.run_id = run_id
                stats.analyzed_at = datetime.now().isoformat()
                
                run_dir = JOBS_DIR / job_name / 'runs' / run_id
                generator = ReportGenerator(stats, run_dir)
                generator.save_json()
                generator.save_html()
                
                log("✓ 报告生成完成")
            except Exception as e:
                log(f"报告生成失败: {str(e)}")
        
    except Exception as e:
        log(f"爬虫错误: {str(e)}")
    finally:
        crawler_state['running'] = False
        socketio.emit('crawler_finished', {'job': job_name})


# ==================== Report API ====================

@app.route('/api/reports/<job_name>')
def list_reports(job_name):
    """List all reports for a job"""
    runs_dir = JOBS_DIR / job_name / 'runs'
    reports = []
    
    if runs_dir.exists():
        for run_dir in sorted(runs_dir.iterdir(), reverse=True):
            if run_dir.is_dir():
                report_html = run_dir / 'report.html'
                stats_json = run_dir / 'statistics.json'
                reports.append({
                    'run_id': run_dir.name,
                    'has_report': report_html.exists(),
                    'has_stats': stats_json.exists()
                })
    
    return jsonify(reports)


@app.route('/api/reports/<job_name>/<run_id>/stats')
def get_report_stats(job_name, run_id):
    """Get report statistics JSON"""
    stats_path = JOBS_DIR / job_name / 'runs' / run_id / 'statistics.json'
    if not stats_path.exists():
        return jsonify({'error': '统计数据不存在'}), 404
    
    with open(stats_path, 'r', encoding='utf-8') as f:
        stats = json.load(f)
    
    return jsonify(stats)


# ==================== Config API ====================

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration (sanitized)"""
    if not CONFIG_PATH.exists():
        return jsonify({'error': '配置文件不存在'}), 404
    
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Sanitize sensitive data
    providers = {}
    for name, provider_config in config.get('providers', {}).items():
        providers[name] = {
            'has_accounts': len(provider_config.get('accounts', [])) > 0,
            'rate_limit': provider_config.get('rate_limit', {})
        }
    
    return jsonify({'providers': providers})


@app.route('/api/config/full', methods=['GET'])
def get_full_config():
    """Get full configuration for editing"""
    if not CONFIG_PATH.exists():
        return jsonify({'providers': {}, 'llm': []})
    
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    return jsonify(config)


@app.route('/api/config/provider', methods=['POST'])
def save_provider_config():
    """Save provider configuration"""
    data = request.json
    provider = data.get('provider')
    
    if not provider:
        return jsonify({'error': '缺少 provider 参数'}), 400
    
    # Load existing config
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        config = {'providers': {}, 'llm': []}
    
    if 'providers' not in config:
        config['providers'] = {}
    
    if provider == 'deepseek':
        account = data.get('account', '')
        password = data.get('password', '')
        rate_limit = data.get('rate_limit', 1)
        rate_period = data.get('rate_period', 60)
        
        # Determine if email or mobile
        account_obj = {'password': password}
        if '@' in account:
            account_obj['email'] = account
        else:
            account_obj['mobile'] = account
        
        config['providers']['deepseek'] = {
            'accounts': [account_obj],
            'rate_limit': {
                'max_requests_per_period': rate_limit,
                'period_seconds': rate_period
            }
        }
    
    elif provider == 'doubao':
        api_key = data.get('api_key', '')
        model = data.get('model', 'doubao-pro-32k')
        endpoint_id = data.get('endpoint_id', '')
        rate_limit = data.get('rate_limit', 60)
        rate_period = data.get('rate_period', 60)
        
        config['providers']['doubao'] = {
            'accounts': [{'api_key': api_key}],
            'model': model,
            'endpoint_id': endpoint_id,
            'base_url': 'https://ark.cn-beijing.volces.com/api/v3',
            'rate_limit': {
                'max_requests_per_period': rate_limit,
                'period_seconds': rate_period
            }
        }
    
    # Save config
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    return jsonify({'success': True, 'message': f'{provider} 配置已保存'})


@app.route('/api/config/llm', methods=['POST'])
def save_llm_config():
    """Save LLM configuration"""
    data = request.json
    
    base_url = data.get('base_url', '')
    api_key = data.get('api_key', '')
    model = data.get('model', '')
    
    if not base_url or not api_key or not model:
        return jsonify({'error': '缺少必要参数'}), 400
    
    # Load existing config
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        config = {'providers': {}, 'llm': []}
    
    config['llm'] = [{
        'base_url': base_url,
        'api_key': api_key,
        'model': model
    }]
    
    # Save config
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    return jsonify({'success': True, 'message': 'LLM 配置已保存'})


@app.route('/api/config/test/<provider>', methods=['POST'])
def test_provider_connection(provider):
    """Test provider connection"""
    try:
        if not CONFIG_PATH.exists():
            return jsonify({'success': False, 'error': '配置文件不存在'})
        
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if provider not in config.get('providers', {}):
            return jsonify({'success': False, 'error': f'{provider} 未配置'})
        
        # For now just check if config exists
        provider_config = config['providers'][provider]
        if provider_config.get('accounts'):
            return jsonify({'success': True, 'message': '配置有效'})
        else:
            return jsonify({'success': False, 'error': '未配置账号'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==================== WebSocket Events ====================

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    emit('status', crawler_state)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
