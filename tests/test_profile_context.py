from healthpilot.profile import load_profile_context
from healthpilot.lifestyle import render_daily_plan


def test_context_validated_and_applied_without_writing_sources(tmp_path):
    profile = tmp_path / 'person.yaml'
    context = tmp_path / 'person.md'
    nutrition = tmp_path / 'nutrition.md'
    context.write_text('# Goals\n- Target weight: 75 kg (proposed)\n- Foods to avoid: banana\n')
    nutrition.write_text('- Breakfast: banana\n- Lunch: rice\n')
    profile.write_text(f'name: Person\ndata_sources:\n  profile_context_md_path: {context}\n  nutrition_md_path: {nutrition}\n')
    before = context.read_bytes()
    loaded = load_profile_context(str(profile), home_dir=tmp_path)
    assert loaded.cache_payload['sources']['profile_context_md_path']['status'] == 'available'
    report = render_daily_plan(profile_slug='person', profile_name='Person', generated_at='2026-09-09', target_date='2026-09-09', evidence_snapshot=loaded.cache_payload)
    assert 'Breakfast: banana' not in report
    assert 'Lunch: rice' in report
    assert context.read_bytes() == before
    context.unlink()
    loaded = load_profile_context(str(profile), home_dir=tmp_path)
    report = render_daily_plan(profile_slug='person', profile_name='Person', generated_at='2026-09-09', target_date='2026-09-09', evidence_snapshot=loaded.cache_payload)
    assert 'Profile context is unavailable' in report
    assert 'Lunch: rice' in report

    profile.write_text(f'name: Person\ndata_sources:\n  nutrition_md_path: {nutrition}\n')
    loaded = load_profile_context(str(profile), home_dir=tmp_path)
    assert loaded.cache_payload['sources']['profile_context_md_path']['status'] == 'not configured'
    report = render_daily_plan(profile_slug='person', profile_name='Person', generated_at='2026-09-09', target_date='2026-09-09', evidence_snapshot=loaded.cache_payload)
    assert 'Profile context is unavailable' in report
