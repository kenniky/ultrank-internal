from startgg_toolkit import send_request
from retrieve_challonge import request_challonge, challongekey
from retrieve_startgg import get_sets


class SetPrerequisite:
    PREREQ_SET = "set"
    PREREQ_SEED = "seed"
    PREREQ_BYE = "bye"

    def __init__(self, type, id_):
        self.type = type
        self.id_ = id_

    def __hash__(self):
        return hash((self.type, self.id_))

    def __str__(self):
        return f'Prereq {self.type} - {self.id_}'


class Set:
    def __init__(self, id_, phase, started_at, completed_at, prereqs):
        self.id_ = id_
        self.phase = phase
        self.started_at = started_at
        self.completed_at = completed_at
        self.prereqs = prereqs

        if started_at is None and completed_at is None:
            self.completed_at = 0

    def get_prerequisite_sets(self):
        return [prereq.id_ for prereq in self.prereqs if prereq.type == SetPrerequisite.PREREQ_SET]

    def get_prerequisite_phases(self):
        prereq_phases = []
        for prereq in self.prereqs:
            if prereq.type == SetPrerequisite.PREREQ_SEED:
                prereq_phase = get_seed_phase_source(prereq.id_)
                if prereq_phase is not None:
                    prereq_phases.append(prereq_phase)

        return prereq_phases

    def __hash__(self):
        return hash((self.id_, self.phase, self.started_at, self.completed_at, self.prereqs))

    def __str__(self):
        return f'Set {self.id_} / Phase {self.phase} / Start {self.started_at} / Completed {self.completed_at} / Prereqs {", ".join([str(prereq) for prereq in self.prereqs])}'

def seed_query(id_):
    query = '''query getSeed($id: ID!) {
        seed (id: $id) {
            progressionSource {
                originPhase {
                    id
                }
            }
        }
    }
    '''

    variables = '''{{
        "id": "{}"
    }}'''.format(id_)
    
    return query, variables

def set_query(id_):
    query = '''query getSet($id: ID!) {
        set (id: $id) {
            id
            startedAt
            completedAt
            slots {
                prereqType
                prereqId
            }
            phaseGroup {
                phase {
                    id
                }
            }
        }
    }'''

    variables = '''{{
        "id": "{}"
    }}'''.format(id_)

    return query, variables

def set_bulk_query(slug, page_num=1, per_page=200, phases=None, phase_groups=None):
    query = '''query getSets($eventSlug: String!, $pageNum: Int!, $perPage: Int!, $phases: [ID]!, $phaseGroups: [ID]!) {
  event (slug: $eventSlug) {
    sets (page: $pageNum, perPage: $perPage, filters: { phaseIds: $phases, phaseGroupIds: $phaseGroups }){
      pageInfo {
        totalPages
      }
      nodes {
        id
        startedAt
        completedAt
        slots {
          prereqType
          prereqId
        }
        phaseGroup {
          phase {
            id
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
        "phases": {},
        "phaseGroups": {}
    }}'''.format(slug, page_num, per_page, f'{phases if phases is not None else "[]"}', f'{phase_groups if phase_groups is not None else "[]"}')
    return query, variables

def get_seed_phase_source(seed_id):
    seed_quer, seed_vars = seed_query(seed_id)
    resp = send_request(seed_quer, seed_vars)

    if resp['data']['seed']['progressionSource'] is None:
        return None
    if resp['data']['seed']['progressionSource']['originPhase'] is None:
        return None
    return resp['data']['seed']['progressionSource']['originPhase']['id']

def get_set_data(set_id):
    set_data_query, set_data_vars = set_query(set_id)
    resp = send_request(set_data_query, set_data_vars)

    resp_set = resp['data']['set']

    prereqs = [SetPrerequisite(pr['prereqType'], str(pr['prereqId'])) for pr in resp_set['slots']]

    return Set(str(resp_set['id']), resp_set['phaseGroup']['phase']['id'], resp_set['startedAt'], resp_set['completedAt'], prereqs)

def get_set_data_bulk(slug, phases=None, phase_groups=None):
    sets = {}
    page = 0

    while True:
        query, variables = set_bulk_query(slug, page_num=page, phases=phases, phase_groups=phase_groups)
        resp = send_request(query, variables)

        try:
            for set_data in resp['data']['event']['sets']['nodes']:
                prereqs = [SetPrerequisite(pr['prereqType'], str(pr['prereqId'])) for pr in set_data['slots']]

                sets[str(set_data['id'])] = Set(str(set_data['id']), set_data['phaseGroup']['phase']['id'], set_data['startedAt'], set_data['completedAt'], prereqs)
      
        except Exception as e:
            print(e)
            print(resp)
            sys.exit()

        if page >= resp['data']['event']['sets']['pageInfo']['totalPages']:
            break
        page += 1

    clean_byes(sets)

    return sets

def generate_order(relations, initial_sort_key=lambda x: x, additional=[]):
    relations_dict = {}
    indegree_dict = {}
    for rel in relations:
        if rel[0] not in relations_dict:
            relations_dict[rel[0]] = set()
        if rel[1] not in relations_dict:
            relations_dict[rel[1]] = set()
        if rel[0] not in indegree_dict:
            indegree_dict[rel[0]] = 0
        if rel[1] not in indegree_dict:
            indegree_dict[rel[1]] = 0

        relations_dict[rel[0]].add(rel[1])
        indegree_dict[rel[1]] += 1

    for item in additional:
        if item not in relations_dict:
            relations_dict[item] = set()
        if item not in indegree_dict:
            indegree_dict[item] = 0

    # print(indegree_dict)

    ordering = []
    for item, indeg in indegree_dict.items():
        if indeg == 0:
            ordering.append(item)
    # print(ordering)

    ordering.sort(key=initial_sort_key)
    for item in ordering:
        for out_item in relations_dict[item]:
            indegree_dict[out_item] -= 1
        indegree_dict.pop(item)

    while len(indegree_dict) > 0:
        next_to_add = None
        for item, indeg in indegree_dict.items():
            if indeg == 0:
                next_to_add = item
                break
        if next_to_add is None:
            raise Exception
        ordering.append(next_to_add)
        for out_item in relations_dict[next_to_add]:
            indegree_dict[out_item] -= 1
        indegree_dict.pop(next_to_add)

    return ordering


def clean_byes(sets_dict):
    # byes are weird
    for set_obj in sets_dict.values():
        for prereq in set_obj.prereqs:
            while prereq.type == SetPrerequisite.PREREQ_SET and prereq.id_ not in sets_dict:
                unknown_set = get_set_data(prereq.id_)
                valid_prereqs = [prereq_ for prereq_ in unknown_set.prereqs if prereq_.type != SetPrerequisite.PREREQ_BYE]
                assert len(valid_prereqs) == 1, f'error retrieving data for {str(set_obj)}\nissue with {str(unknown_set)}'
                prereq.type = valid_prereqs[0].type
                prereq.id_ = valid_prereqs[0].id_


def get_set_order_startgg(sets):
    # sets = {}
    # for id_ in set_ids:
    #     sets[str(id_)] = get_set_data(id_)
    # clean_byes(sets)

    # progressions are stored earlier, later
    set_progressions = {}
    sets_by_phase = {}
    phases = set()
    phase_progressions = set()

    for set_ in sets.values():
        phases.add(set_.phase)
        if set_.phase not in sets_by_phase:
            sets_by_phase[set_.phase] = set()
        if set_.phase not in set_progressions:
            set_progressions[set_.phase] = set()
        sets_by_phase[set_.phase].add(set_.id_)

        for prereq_set in set_.get_prerequisite_sets():
            set_progressions[set_.phase].add((prereq_set, set_.id_))
        for prereq_phase in set_.get_prerequisite_phases():
            phase_progressions.add((prereq_phase, set_.phase))

    # print(phases)

    phase_set_orders = {}
    for phase in phases:
        set_progs = set_progressions[phase]
        set_list = sets_by_phase[phase]

        comp_via_completed = False
        for set_ in set_list:
            if sets[set_].started_at is None:
                comp_via_completed = True
                break
        comp_key = (lambda set_: sets[set_].completed_at) if comp_via_completed else (lambda set_: sets[set_].started_at)
        phase_set_orders[phase] = generate_order(set_progs, initial_sort_key=comp_key, additional=set_list)

    # print(list(phase_set_orders.keys()))

    if len(phase_progressions) > 0:
        phase_order = generate_order(phase_progressions)
    else:
        phase_order = list(set_progressions.keys())

    # print(phase_order)

    final_order = []
    for phase in phase_order:
        final_order.extend(phase_set_orders.get(phase, []))

    return final_order

def get_tournament_set_order_challonge(slug):
    url = 'https://api.challonge.com/v1/tournaments/{}/matches.json?api_key={}'.format(slug, challongekey)
    data = request_challonge(url)

    set_progressions = set()
    for set_ in data:
        set_data = set_['match']
        if set_data['player1_prereq_match_id'] is not None:
            set_progressions.add((set_data['player1_prereq_match_id'], set_data['id']))
        if set_data['player2_prereq_match_id'] is not None:
            set_progressions.add((set_data['player2_prereq_match_id'], set_data['id']))

    return generate_order(set_progressions)

def get_tournament_set_order_startgg(slug, phases=None, phase_groups=None):
    sets = get_set_data_bulk(slug, phases=phases, phase_groups=None)

    return get_set_order_startgg(sets)

def get_tournament_set_order_startgg_slow(slug, phases=None):
    sets_raw = get_sets(slug, phases=phases)
    set_ids = [set_['id'] for set_ in sets_raw]
    return get_tournament_set_order_from_ids(set_ids)

def get_tournament_set_order_from_ids(set_ids):
    sets = {}
    for id_ in set_ids:
        sets[str(id_)] = get_set_data(id_)
    clean_byes(sets)

    return get_set_order_startgg(sets)


if __name__ == '__main__':
    print(get_tournament_set_order('tournament/edps-practice-tournament/event/ultimate-singles'))