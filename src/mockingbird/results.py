"""Read final Job verdicts from current and historical result formats."""


def final_results(result):
    if result.get('schema_version', 0) >= 4:
        return [entry['result'] for entry in result['jobs'].values()
                if entry['state'] == 'COMPLETE']
    return result.get('tests', [])
