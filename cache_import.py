"""Create a clean role profile for legacy cache replacement only."""
import os
import uuid
import role_reader


def fresh_role(prepare_fn, base, game, identity, servers):
    account_id = uuid.uuid4().hex
    profile, cwd, env = prepare_fn(base, game, account_id)
    cache = profile / 'AppData/Roaming/Netease/Mpay'
    if any(cache.iterdir()):
        raise ValueError('新角色的登录目录不是空目录，已停止处理')
    config_file = cwd / 'Documents/clientconfig'
    config = role_reader.read_client_config(config_file) if config_file.exists() else {}
    entry = next((s for s in servers if str(s['id']) == identity['server_id']), {})
    # Only select the destination server. Do not seed login history or SDK accounts.
    config.update({'local_all_login_record': {}, 'areaSetId': identity['server_id'],
                   'areaSet': entry.get('internalName') or identity['server'], 'swith_areaSetId': ''})
    import json
    temp = config_file.with_name('clientconfig.import.tmp')
    temp.write_text(json.dumps(config, ensure_ascii=False, separators=(',', ':')).encode('utf-8').hex(), encoding='utf-8')
    os.replace(temp, config_file)
    return {'id': account_id, 'name': identity['nickname'], **identity,
            'confirmed': False, 'imported': True, 'cache_mode': 'fresh-single-role',
            'target_short_id': identity['short_id'], 'target_server_id': identity['server_id']}
