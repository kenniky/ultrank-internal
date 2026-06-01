from startgg_toolkit import send_request, isolate_slug, InvalidEventUrlException
import sys
import uuid
import os
import csv

class DuplicateIdException(Exception):
    pass

def phase_groups_query(event_slug):
    query = '''query getPhaseGroups($eventSlug: String!) {
  event(slug: $eventSlug) {
    phaseGroups {
      id
      phase {
        isExhibition
      }
    }
  }
}'''
    variables = '''{{
        "eventSlug": "{}"
    }}'''.format(event_slug)

    return query, variables

def placements_query(event_slug, page_num=1, per_page=50):
    query = '''query getPlacements($eventSlug: String!, $pageNum: Int!, $perPage: Int!) {
  event(slug: $eventSlug) {
    standings (query: { page: $pageNum, perPage: $perPage }) {
      pageInfo {
        totalPages
      }
      nodes {
        player {
          id
          gamerTag
        }
        placement
      }
    }
  }
}'''
    variables = '''{{
        "eventSlug": "{}",
        "pageNum": {},
        "perPage": {}
    }}'''.format(event_slug, page_num, per_page)

    return query, variables

def sets_phase_group_query(phase_group_id, page_num=1, per_page=50):
    query = '''query getSets($phaseGroup: ID!, $pageNum: Int!, $perPage: Int!) {
  phaseGroup (id: $phaseGroup) {
    id
    sets (page: $pageNum, perPage: $perPage){
      pageInfo {
        totalPages
      }
      nodes {
        id
        winnerId
        slots {
          entrant {
            id
            participants {
              player {
                gamerTag
                id
              }
            }
          }
          standing {
            stats {
                score {
                value
              }
            }
          }
        }
      }
    }
  }
}'''
    variables = '''{{
        "phaseGroup": "{}",
        "pageNum": {},
        "perPage": {}
    }}'''.format(phase_group_id, page_num, per_page)
    return query, variables


def sets_query(event_slug, page_num=1, per_page=50, phases=None):
    query = '''query getSets($eventSlug: String!, $pageNum: Int!, $perPage: Int!, $phases: [ID]!) {
  event (slug: $eventSlug) {
    sets (page: $pageNum, perPage: $perPage, filters: { phaseIds: $phases }){
      pageInfo {
        totalPages
      }
      nodes {
        id
        winnerId
        slots {
          entrant {
            id
            participants {
              player {
                gamerTag
                id
              }
            }
          }
          standing {
            stats {
                score {
                value
              }
            }
          }
        }
      }
    }
  }
}'''
    variables = '''{{
        "eventSlug": "{}",
        "pageNum": {},
        "perPage": {},
        "phases": {}
    }}'''.format(event_slug, page_num, per_page, f'{phases if phases is not None else "[]"}')
    return query, variables

def set_query(set_id):
    query = '''query getSet($id: ID!) {
  set(id: $id) {
    event {
      slug
    }
    id
    winnerId
    slots {
      entrant {
        id
        participants {
          player {
            gamerTag
            id
          }
        }
      }
      standing {
        stats {
          score {
            value
          }
        }
      }
    }
  }
}'''
    variables = '''{{
        "id": {}
    }}'''.format(set_id)
    return query, variables

def phase_list_query(event_slug):
    query = '''query getPhases($eventSlug: String!) {
  event(slug: $eventSlug) {
    phases {
      id
      name
      isExhibition
    }
  }
}'''
    variables = '''{{
        "eventSlug": "{}"
    }}'''.format(event_slug)

    return query, variables

def get_placements(event_slug, merges={}):
    page = 1

    placements = []

    ids = set()

    while True:
        query, variables = placements_query(event_slug, page_num=page)
        resp = send_request(query, variables)

        try:
            for placement_data in resp['data']['event']['standings']['nodes']:
                if placement_data['player'] is None:
                    print(placement_data)
                    placeholder = uuid.uuid4().hex
                    placement_data['player'] = {'id': placeholder, 'gamerTag': placeholder}
                if placement_data['player']['id'] in ids:
                    print(f"error: duplicate player id {placement_data['player']['id']} - {placement_data['player']['gamerTag']}")
                    raise DuplicateIdException()
                placements.append({'placement': placement_data['placement'], 'id': merges.get(str(placement_data['player']['id']), str(placement_data['player']['id'])), 'tag': placement_data['player']['gamerTag']})
        except Exception as e:
            print(e)
            print(resp)
            sys.exit()

        if page >= resp['data']['event']['standings']['pageInfo']['totalPages']:
            break
        page += 1

    return placements 

def get_set(set_id, merges={}, include_event_slug=False):
    query, variables = set_query(set_id)
    resp = send_request(query, variables)

    set_data = resp['data']['set']

    try:
        p1_set_id = set_data['slots'][0]['entrant']['id']
        p2_set_id = set_data['slots'][1]['entrant']['id']

        if len(set_data['slots'][0]['entrant']['participants']) == 0:
            seedId = f"seed{set_data['slots'][0]['entrant']['id']}"
            set_data['slots'][0]['entrant']['participants'].append({'player': {'id': seedId, 'gamerTag': seedId}})
        if len(set_data['slots'][1]['entrant']['participants']) == 0:
            seedId = f"seed{set_data['slots'][1]['entrant']['id']}"
            set_data['slots'][1]['entrant']['participants'].append({'player': {'id': seedId, 'gamerTag': seedId}})

        p1_orig_id = str(set_data['slots'][0]['entrant']['participants'][0]['player']['id'])
        p2_orig_id = str(set_data['slots'][1]['entrant']['participants'][0]['player']['id'])
        p1_id = merges.get(p1_orig_id, p1_orig_id)
        p2_id = merges.get(p2_orig_id, p2_orig_id)

        return {'event_slug': set_data['event']['slug'], 'id': set_data['id'], 'winner': None if set_data['winnerId'] == None else p1_id if set_data['winnerId'] == p1_set_id else p2_id,
            'p1_id': p1_id, 'p1_tag': set_data['slots'][0]['entrant']['participants'][0]['player']['gamerTag'], 'p1_score': set_data['slots'][0]['standing']['stats']['score']['value'],
            'p2_id': p2_id, 'p2_tag': set_data['slots'][1]['entrant']['participants'][0]['player']['gamerTag'], 'p2_score': set_data['slots'][1]['standing']['stats']['score']['value']}

    except Exception as e:
        print(e)
        print(resp)
        sys.exit()

def get_sets_from_phase_groups(phase_groups, merges={}):
    sets = []

    for phase_group in phase_groups:
        page = 1

        while True:
            query, variables = sets_phase_group_query(phase_group, page_num=page)
            resp = send_request(query, variables)

            try:
                for set_data in resp['data']['phaseGroup']['sets']['nodes']:
                    if len(set_data['slots']) < 2:
                        continue

                    if set_data['slots'][0]['entrant'] == None or set_data['slots'][1]['entrant'] == None:
                        continue

                    if len(set_data['slots'][0]['entrant']['participants']) == 0:
                        seedId = f"seed{set_data['slots'][0]['entrant']['id']}"
                        set_data['slots'][0]['entrant']['participants'].append({'player': {'id': seedId, 'gamerTag': seedId}})
                    if len(set_data['slots'][1]['entrant']['participants']) == 0:
                        seedId = f"seed{set_data['slots'][1]['entrant']['id']}"
                        set_data['slots'][1]['entrant']['participants'].append({'player': {'id': seedId, 'gamerTag': seedId}})

                    p1_set_id = set_data['slots'][0]['entrant']['id']
                    p2_set_id = set_data['slots'][1]['entrant']['id']
                    p1_orig_id = str(set_data['slots'][0]['entrant']['participants'][0]['player']['id'])
                    p2_orig_id = str(set_data['slots'][1]['entrant']['participants'][0]['player']['id'])
                    p1_id = merges.get(p1_orig_id, p1_orig_id)
                    p2_id = merges.get(p2_orig_id, p2_orig_id)

                    sets.append({'id': set_data['id'], 'winner': None if set_data['winnerId'] == None else p1_id if set_data['winnerId'] == p1_set_id else p2_id, 'p1_id': p1_id, 'p1_tag': set_data['slots'][0]['entrant']['participants'][0]['player']['gamerTag'], 'p1_score': set_data['slots'][0]['standing']['stats']['score']['value'],
                        'p2_id': p2_id, 'p2_tag': set_data['slots'][1]['entrant']['participants'][0]['player']['gamerTag'], 'p2_score': set_data['slots'][1]['standing']['stats']['score']['value']})
            except Exception as e:
                print(e)
                print(resp)
                sys.exit()

            if page >= resp['data']['phaseGroup']['sets']['pageInfo']['totalPages']:
                break
            page += 1

    return sets


def get_sets(event_slug, phases=None, merges={}):
    page = 1

    sets = []

    while True:
        query, variables = sets_query(event_slug, page_num=page, phases=phases)
        resp = send_request(query, variables)

        try:
            for set_data in resp['data']['event']['sets']['nodes']:
                if len(set_data['slots']) < 2:
                    continue
                
                if set_data['slots'][0]['entrant'] == None or set_data['slots'][1]['entrant'] == None:
                    continue

                if len(set_data['slots'][0]['entrant']['participants']) == 0:
                    seedId = f"seed{set_data['slots'][0]['entrant']['id']}"
                    set_data['slots'][0]['entrant']['participants'].append({'player': {'id': seedId, 'gamerTag': seedId}})
                if len(set_data['slots'][1]['entrant']['participants']) == 0:
                    seedId = f"seed{set_data['slots'][1]['entrant']['id']}"
                    set_data['slots'][1]['entrant']['participants'].append({'player': {'id': seedId, 'gamerTag': seedId}})

                p1_set_id = set_data['slots'][0]['entrant']['id']
                p2_set_id = set_data['slots'][1]['entrant']['id']
                p1_orig_id = str(set_data['slots'][0]['entrant']['participants'][0]['player']['id'])
                p2_orig_id = str(set_data['slots'][1]['entrant']['participants'][0]['player']['id'])
                p1_id = merges.get(p1_orig_id, p1_orig_id)
                p2_id = merges.get(p2_orig_id, p2_orig_id)

                sets.append({'id': set_data['id'], 'winner': None if set_data['winnerId'] == None else p1_id if set_data['winnerId'] == p1_set_id else p2_id, 'p1_id': p1_id, 'p1_tag': set_data['slots'][0]['entrant']['participants'][0]['player']['gamerTag'], 'p1_score': set_data['slots'][0]['standing']['stats']['score']['value'],
                    'p2_id': p2_id, 'p2_tag': set_data['slots'][1]['entrant']['participants'][0]['player']['gamerTag'], 'p2_score': set_data['slots'][1]['standing']['stats']['score']['value']})
        except Exception as e:
            print(e)
            print(resp)
            sys.exit()

        if page >= resp['data']['event']['sets']['pageInfo']['totalPages']:
            break
        page += 1

    return sets

def collect_phase_groups(event_slug):
    query, variables = phase_groups_query(event_slug)
    resp = send_request(query, variables)

    return [phase_group['id'] for phase_group in resp['data']['event']['phaseGroups'] if not phase_group['phase']['isExhibition']]

def collect_phases(event_slug):
    # Collects phases that are part of the main tournament. (Hopefully) excludes amateur brackets.

    # Get ordered list of phases
    query, variables = phase_list_query(event_slug)
    resp = send_request(query, variables)

    return [phase for phase in resp['data']['event']['phases'] if not phase['isExhibition']]

def strip_phase_ids(phases):
    return [phase['id'] for phase in phases]

def read_merges():
    merge_file_name = input('input merges file: ')

    merges = {}
    try:
        with open(merge_file_name, newline='') as merges_file:
            merges_reader = csv.DictReader(merges_file)

            for row in merges_reader:
                merges[row['from']] = row['to']

    except:
        pass

    return merges

def get_single_tournament_flow():
    event_slug = isolate_slug(input('input event slug: '))

    merges = read_merges()

    phases = collect_phases(event_slug)

    print('using phases {}'.format(str([phase['name'] for phase in phases])))

    placements = get_placements(event_slug, merges)

    with open('tour_placements.csv', newline='', mode='w', encoding='utf-8') as placements_file:
        placements_csv = csv.DictWriter(placements_file, ['placement', 'id', 'tag'])
        placements_csv.writeheader()

        for placement in placements:
            placements_csv.writerow(placement)

    sets = get_sets(event_slug, [phase['id'] for phase in phases], merges)

    with open('tour_sets.csv', newline='', mode='w') as sets_file:
        sets_csv = csv.DictWriter(sets_file, ['id', 'winner', 'p1_id', 'p1_tag', 'p1_score', 'p2_id', 'p2_tag', 'p2_score'])
        sets_csv.writeheader()

        for set_ in sets:
            sets_csv.writerow(set_)

def get_multiple_tournaments_flow():
    input_file_name = input('input file with urls: ')
    input_file = open(input_file_name)
    merges = read_merges()

    if not os.path.exists('tournament_data'):
        os.mkdir('tournament_data')

    for i, row in enumerate(input_file):
        try:
            event_slug = isolate_slug(row)
        except InvalidEventUrlException:
            print(f'skipping line {i} since unable to parse url')
            continue

        file_slug = event_slug.replace('tournament/', '', 1).replace('/event/', '__')

        print(f'({i}) retrieving {file_slug}')

        phases = collect_phases(event_slug)

        print('  using phases {}'.format(str([phase['name'] for phase in phases])))

        placements = get_placements(event_slug, merges)

        with open(f'tournament_data/{file_slug}_placements.csv', newline='', mode='w', encoding='utf-8') as placements_file:
            placements_csv = csv.DictWriter(placements_file, ['placement', 'id', 'tag'])
            placements_csv.writeheader()

            for placement in placements:
                placements_csv.writerow(placement)

        sets = get_sets(event_slug, [phase['id'] for phase in phases], merges)

        with open(f'tournament_data/{file_slug}_sets.csv', newline='', mode='w') as sets_file:
            sets_csv = csv.DictWriter(sets_file, ['id', 'winner', 'p1_id', 'p1_tag', 'p1_score', 'p2_id', 'p2_tag', 'p2_score'])
            sets_csv.writeheader()

            for set_ in sets:
                sets_csv.writerow(set_)

        print('  retrieved')

if __name__ == '__main__':
    get_multiple_tournaments_flow()