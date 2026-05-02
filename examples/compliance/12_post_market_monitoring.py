import os
import sys

# Ensure lar module can be found
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from lar.compliance.incident_reporter import IncidentReporter

def main():
    print("="*60)
    print(" Lár - EU AI Act Art 72 Post-Market Monitoring")
    print("="*60)
    
    # We point the reporter at the directory where our enterprise backbone saves logs
    log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src/lar/enterprise/enterprise_audit'))
    
    if not os.path.exists(log_dir):
        print(f"Directory not found: {log_dir}")
        print("Please run `python src/lar/enterprise/run.py FINANCE` first to generate some logs.")
        return
        
    print(f"\nScanning logs in: {log_dir}...\n")
    
    reporter = IncidentReporter(log_dir)
    report_markdown = reporter.generate_report()
    
    # Output to console
    print(report_markdown)
    
    # Save report to file
    report_path = os.path.join(log_dir, "incident_report_latest.md")
    with open(report_path, "w") as f:
        f.write(report_markdown)
        
    print(f"\n[+] Report saved to {report_path}")
    print("="*60)

if __name__ == "__main__":
    main()
