import logging

import pandas as pd
import pytest
from aizynthfinder.aizynthfinder import AiZynthFinder


def state_smiles(state):
    return [mol.smiles for mol in state.mols]


def test_reset_tree():
    finder = AiZynthFinder()
    finder.target_smiles = "CCCO"
    finder.prepare_tree()

    assert finder.tree is not None

    finder.target_smiles = "CCO"

    assert finder.tree is None


def test_dead_end_expansion(setup_aizynthfinder):
    """
    Test the building of this tree:
                root
    root cannot be expanded
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    lookup = {root_smi: []}
    finder = setup_aizynthfinder(lookup, [])

    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 1
    assert state_smiles(nodes[0].state) == [root_smi]
    assert finder.search_stats["iterations"] == 100
    assert nodes[0].created_at_iteration == 0


def test_freeze_bond_not_in_target_mol(setup_aizynthfinder):
    root_smi = "CN1CCC(C(=O)c2cccc([NH:1][C:2](=O)c3ccc(F)cc3)c2F)CC1"
    lookup = {root_smi: []}
    finder = setup_aizynthfinder(lookup, [])
    finder.config.search.freeze_bonds = [(2, 3)]

    with pytest.raises(
        ValueError, match=r"Bonds in \'freeze_bond\' must exist in target molecule"
    ):
        finder.prepare_tree()


def test_break_bond_not_in_target_mol(setup_aizynthfinder):
    root_smi = "CN1CCC(C(=O)c2cccc([NH:1][C:2](=O)c3ccc(F)cc3)c2F)CC1"
    lookup = {root_smi: []}
    finder = setup_aizynthfinder(lookup, [])
    finder.config.search.break_bonds = [(2, 3)]
    finder.config.search.algorithm_config["search_rewards"] = [
        "state score",
        "broken bonds",
    ]

    with pytest.raises(
        ValueError, match=r"Bonds in \'break_bonds\' must exist in target molecule"
    ):
        finder.prepare_tree()


def test_broken_frozen_bond_filter(setup_aizynthfinder, shared_datadir):
    root_smi = "CN1CCC(C(=O)c2cccc([NH:1][C:2](=O)c3ccc(F)cc3)c2F)CC1"

    reaction_template = pd.read_csv(
        shared_datadir / "test_reactions_template.csv", sep="\t"
    )
    template1_smarts = reaction_template["RetroTemplate"][0]
    template2_smarts = reaction_template["RetroTemplate"][1]

    child1_smi = ["N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "CN1CCC(Cl)CC1", "O"]
    child2_smi = ["N#Cc1cccc(N)c1F", "O=C(Cl)c1ccc(F)cc1"]

    lookup = {
        root_smi: {"smarts": template1_smarts, "prior": 1.0},
        child1_smi[0]: {
            "smarts": template2_smarts,
            "prior": 1.0,
        },
    }

    finder = setup_aizynthfinder(lookup, [child1_smi[1], child1_smi[2]] + child2_smi)
    finder.config.search.freeze_bonds = [(1, 2)]
    finder.config.search.return_first = True
    finder.prepare_tree()
    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 2
    assert state_smiles(nodes[0].state) == [root_smi]
    assert sorted(state_smiles(nodes[1].state)) == sorted(child1_smi)
    assert finder.search_stats["iterations"] == 100

    assert finder.filter_policy.selection == ["dummy", "__finder_bond_filter"]
    assert not finder.search_stats["returned_first"]


def test_non_broken_frozen_bond_filter(setup_aizynthfinder, shared_datadir):
    root_smi = "CN1CCC(C(=O)c2cccc([NH:1][C:2](=O)c3ccc(F)cc3)c2F)CC1"

    reaction_template = pd.read_csv(
        shared_datadir / "test_reactions_template.csv", sep="\t"
    )
    template1_smarts = reaction_template["RetroTemplate"][0]
    template2_smarts = reaction_template["RetroTemplate"][2]

    child1_smi = ["N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "CN1CCC(Cl)CC1", "O"]
    child2_smi = ["N#Cc1cccc(Cl)c1F", "NC(=O)c1ccc(F)cc1"]

    lookup = {
        root_smi: {"smarts": template1_smarts, "prior": 1.0},
        child1_smi[0]: {
            "smarts": template2_smarts,
            "prior": 1.0,
        },
    }

    finder = setup_aizynthfinder(lookup, [child1_smi[1], child1_smi[2]] + child2_smi)
    finder.config.search.freeze_bonds = [(1, 2)]
    finder.config.search.return_first = True
    finder.prepare_tree()
    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 3
    assert state_smiles(nodes[0].state) == [root_smi]
    assert sorted(state_smiles(nodes[1].state)) == sorted(child1_smi)
    assert sorted(state_smiles(nodes[2].state)) == sorted(
        [child1_smi[1], child1_smi[2]] + child2_smi
    )
    assert finder.search_stats["iterations"] == 1

    assert finder.filter_policy.selection == ["dummy", "__finder_bond_filter"]
    assert finder.search_stats["returned_first"]


def test_one_expansion(setup_aizynthfinder):
    """
    Test the building of this tree:
                root
                  |
                child 1
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child1_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    lookup = {root_smi: {"smiles": ".".join(child1_smi), "prior": 1.0}}
    finder = setup_aizynthfinder(lookup, child1_smi)

    # Test first with return_first
    finder.config.search.return_first = True
    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 2
    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert nodes[0].created_at_iteration == 0
    assert nodes[1].created_at_iteration == 1
    assert finder.search_stats["iterations"] == 1
    assert finder.search_stats["returned_first"]

    # then test with iteration limit
    finder.config.search.return_first = False
    finder.config.search.iteration_limit = 45
    finder.prepare_tree()
    finder.tree_search()

    assert len(finder.tree.graph()) == 2
    assert finder.search_stats["iterations"] == 45
    assert not finder.search_stats["returned_first"]


def test_two_expansions(setup_aizynthfinder):
    """
    Test the building of this tree:
                root
                  |
                child 1
                  |
                child 2
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child1_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    child2_smi = ["N#Cc1cccc(N)c1F", "O=C(Cl)c1ccc(F)cc1"]
    lookup = {
        root_smi: {"smiles": ".".join(child1_smi), "prior": 1.0},
        child1_smi[1]: {"smiles": ".".join(child2_smi), "prior": 1.0},
    }
    finder = setup_aizynthfinder(lookup, [child1_smi[0], child1_smi[2]] + child2_smi)
    finder.config.search.return_first = True

    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 3
    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert state_smiles(nodes[2].state) == [child1_smi[0], child1_smi[2]] + child2_smi
    assert finder.search_stats["iterations"] == 1


def test_two_expansions_two_children(setup_aizynthfinder):
    """
    Test the building of this tree:
                root
            /           \
        child 1        child 2
            |             |
        grandchild 1   grandchild 2
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child1_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    child2_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F"]
    grandchild_smi = ["N#Cc1cccc(N)c1F", "O=C(Cl)c1ccc(F)cc1"]
    lookup = {
        root_smi: [
            {"smiles": ".".join(child1_smi), "prior": 0.7},
            {"smiles": ".".join(child2_smi), "prior": 0.3},
        ],
        child1_smi[1]: {"smiles": ".".join(grandchild_smi), "prior": 0.7},
        child2_smi[1]: {"smiles": ".".join(grandchild_smi), "prior": 0.7},
    }
    finder = setup_aizynthfinder(
        lookup, [child1_smi[0], child1_smi[2]] + grandchild_smi
    )

    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 5
    assert nodes[0].created_at_iteration == 0
    assert nodes[1].created_at_iteration == 1
    assert nodes[2].created_at_iteration == 1
    assert nodes[3].created_at_iteration == 2
    assert nodes[4].created_at_iteration == 2

    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert (
        state_smiles(nodes[2].state) == [child1_smi[0], child1_smi[2]] + grandchild_smi
    )
    assert state_smiles(nodes[3].state) == child2_smi
    assert state_smiles(nodes[4].state) == [child2_smi[0]] + grandchild_smi
    assert finder.search_stats["iterations"] == 100

    # then test with immediate expansion
    finder.config.search.algorithm_config["immediate_instantiation"] = [
        "simple_expansion"
    ]
    finder.prepare_tree()
    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 5
    assert nodes[0].created_at_iteration == 0
    assert nodes[1].created_at_iteration == 1
    assert nodes[2].created_at_iteration == 1
    assert nodes[3].created_at_iteration == 1
    assert nodes[4].created_at_iteration == 2


def test_three_expansions(setup_aizynthfinder):
    """
    Test the building of this tree:
                root
                  |
                child 1
                  |
                child 2
                  |
                child 3 (*)
        - child 3 state is solved
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child1_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    child2_smi = ["N#Cc1cccc(N)c1F", "O=C(Cl)c1ccc(F)cc1"]
    child3_smi = ["O=C(Cl)c1ccccc1"]
    lookup = {
        root_smi: {"smiles": ".".join(child1_smi), "prior": 1.0},
        child1_smi[1]: {"smiles": ".".join(child2_smi), "prior": 1.0},
        child2_smi[1]: {"smiles": child3_smi[0], "prior": 1.0},
    }
    finder = setup_aizynthfinder(
        lookup, [child1_smi[0], child1_smi[2], child2_smi[0]] + child3_smi
    )
    finder.config.search.return_first = True

    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 4
    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert state_smiles(nodes[2].state) == [child1_smi[0], child1_smi[2]] + child2_smi
    expected_list = [child1_smi[0], child1_smi[2], child2_smi[0]] + child3_smi
    assert state_smiles(nodes[3].state) == expected_list
    assert nodes[3].state.is_solved
    assert finder.search_stats["iterations"] == 1


def test_three_expansions_not_solved(setup_aizynthfinder):
    """
    Test the building of this tree:
                root
                  |
                child 1
                  |
                child 2
                  |
                child 3
        - child 3 state is not solved (not in stock)
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child1_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    child2_smi = ["N#Cc1cccc(N)c1F", "O=C(Cl)c1ccc(F)cc1"]
    child3_smi = ["O=C(Cl)c1ccccc1"]
    lookup = {
        root_smi: {"smiles": ".".join(child1_smi), "prior": 1.0},
        child1_smi[1]: {"smiles": ".".join(child2_smi), "prior": 1.0},
        child2_smi[1]: {"smiles": child3_smi[0], "prior": 1.0},
    }
    finder = setup_aizynthfinder(lookup, [child1_smi[0], child1_smi[2], child2_smi[0]])
    finder.config.search.return_first = True
    finder.config.search.max_transforms = 3
    finder.config.search.iteration_limit = 15

    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 4
    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert state_smiles(nodes[2].state) == [child1_smi[0], child1_smi[2]] + child2_smi
    expected_list = [child1_smi[0], child1_smi[2], child2_smi[0]] + child3_smi
    assert state_smiles(nodes[3].state) == expected_list
    assert not nodes[3].state.is_solved
    assert finder.search_stats["iterations"] == 15


def test_two_expansions_no_expandable_root(setup_aizynthfinder):
    """
    Test the following scenario:
                root
                  |
              child 1 (+)

        - child 1 will be selected first for expansion (iteration 1)
        - it has no children that can be expanded (marked by +)
        -- end of iteration 1
        - iteration 2 starts but selecting a leaf will raise an exception
        -- will continue to iterate until reached number of iteration (set 10 in the test)
        * nodes in tree will be root, child 1
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child1_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    lookup = {
        root_smi: {
            "smiles": ".".join(child1_smi),
            "prior": 1.0,
        },
        child1_smi[1]: {
            "smiles": "",
            "prior": 0.3,
        },
    }
    finder = setup_aizynthfinder(lookup, [child1_smi[0], child1_smi[2]])
    finder.config.search.return_first = True
    finder.config.search.iteration_limit = 10

    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 2
    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert finder.search_stats["iterations"] == 10


def test_two_expansions_no_reactants_first_child(setup_aizynthfinder):
    """
    Test the following scenario:
                root
            /           \
        child 1 (+)        child 2
                             |
                        grandchild 1 (*)

        - child 1 will be selected first for expansion (iteration 1)
        - it has no children that can be expanded (marked by +)
        -- end of iteration 1
        - child 2 will be selected for expansion  (iteration 2)
        - grandchild 1 will be selected next and it is in stock (marked by *)
        -- a solution is found and the tree search is terminated
        * nodes in tree will be root, child1, child2, grandchild 1
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child1_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    child2_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1CF"]
    grandchild1_smi = ["N#Cc1cccc(N)c1F", "O=C(Cl)c1ccc(F)cc1"]
    lookup = {
        root_smi: [
            {"smiles": ".".join(child1_smi), "prior": 0.7},
            {"smiles": ".".join(child2_smi), "prior": 0.3},
        ],
        child1_smi[1]: {
            "smiles": "",
            "prior": 0.3,
        },
        child2_smi[1]: {
            "smiles": ".".join(grandchild1_smi),
            "prior": 0.3,
        },
    }
    finder = setup_aizynthfinder(
        lookup, [child1_smi[0], child1_smi[2]] + grandchild1_smi
    )
    finder.config.search.return_first = True

    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 4
    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert state_smiles(nodes[2].state) == child2_smi
    assert state_smiles(nodes[3].state) == [child2_smi[0]] + grandchild1_smi
    assert finder.search_stats["iterations"] == 2


def test_three_expansions_no_reactants_first_child(setup_aizynthfinder):
    """
    Test the following scenario:
                root
            /           \
        child 1 (+)        child 2
                          |
                    grandchild 1
                          |
                    grandchild 2 (*)

        - child 1 will be selected first for expansion (iteration 1)
        - it has no children that can be expanded (marked by +)
        -- end of iteration 1
        - child 2 will be selected for expansion  (iteration 2)
        - grandchild 1 will be selected next
        - grandchild 2 will be selected next and it is in stock (marked by *)
        -- a solution is found and the tree search is terminated
        * nodes in tree will be root, child1, child2, grandchild 1, grandchild 2
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child1_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    child2_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1CF"]
    grandchild1_smi = ["N#Cc1cccc(N)c1F", "O=C(Cl)c1ccc(F)cc1"]
    grandchild2_smi = ["O=C(Cl)c1ccccc1"]
    lookup = {
        root_smi: [
            {"smiles": ".".join(child1_smi), "prior": 0.7},
            {"smiles": ".".join(child2_smi), "prior": 0.3},
        ],
        child1_smi[1]: {
            "smiles": "",
            "prior": 0.3,
        },
        child2_smi[1]: {
            "smiles": ".".join(grandchild1_smi),
            "prior": 0.3,
        },
        grandchild1_smi[1]: {
            "smiles": ".".join(grandchild2_smi),
            "prior": 1.0,
        },
    }
    finder = setup_aizynthfinder(
        lookup, [child1_smi[0], child1_smi[2], grandchild1_smi[0]] + grandchild2_smi
    )
    finder.config.search.return_first = True

    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 5
    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert state_smiles(nodes[2].state) == child2_smi
    assert state_smiles(nodes[3].state) == [child2_smi[0]] + grandchild1_smi
    expected_list = [child2_smi[0], grandchild1_smi[0]] + grandchild2_smi
    assert state_smiles(nodes[4].state) == expected_list
    assert finder.search_stats["iterations"] == 2


def test_three_expansions_no_reactants_second_level(setup_aizynthfinder):
    """
    Test the following scenario:
                root
            /           \
        child 1         child 2
           |               |
        grandchild 1 (+) grandchild 2 (*)

        - child 1 will be selected first for expansion (iteration 1)
        - grandchild 1 will be selected next,
        - it has no children that can be expanded (marked by x)
        -- end of iteration 1
        - child 2 will be selected for expansion  (iteration 2)
        - grandchild 2 will be selected next and it is in stock (marked by *)
        -- a solution is found and the tree search is terminated
        * nodes in tree will be root, child1, grandchild 1, child2, grandchild 2
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child1_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    child2_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1CF"]
    grandchild1_smi = ["N#Cc1cccc(N)c1F", "O=C(Cl)c1ccc(F)cc1"]
    grandchild2_smi = ["N#Cc1cccc(N)c1", "O=C(Cl)c1ccc(F)c(F)c1"]
    lookup = {
        root_smi: [
            {"smiles": ".".join(child1_smi), "prior": 0.7},
            {"smiles": ".".join(child2_smi), "prior": 0.3},
        ],
        child1_smi[1]: {
            "smiles": ".".join(grandchild1_smi),
            "prior": 0.3,
        },
        grandchild1_smi[1]: {
            "smiles": "",
            "prior": 1.0,
        },
        child2_smi[1]: {
            "smiles": ".".join(grandchild2_smi),
            "prior": 0.3,
        },
    }
    finder = setup_aizynthfinder(
        lookup, [child1_smi[0], child1_smi[2], grandchild1_smi[0]] + grandchild2_smi
    )
    finder.config.search.return_first = True

    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 5
    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert (
        state_smiles(nodes[2].state) == [child1_smi[0], child1_smi[2]] + grandchild1_smi
    )
    assert state_smiles(nodes[3].state) == child2_smi
    assert state_smiles(nodes[4].state) == [child2_smi[0]] + grandchild2_smi
    assert finder.search_stats["iterations"] == 2


def test_two_expansions_no_reactants_second_child(setup_aizynthfinder):
    """
    Test the following scenario:
                root
            /           \
        child 1        child 2 (+)
            |
        grandchild 1 (*)

        - child 1 will be selected first for expansion (iteration 1)
        - grandchild 1 will be selected next and it is in stock (marked by *)
        -- end of iteration 1
        - child 2 will be selected for expansion  (iteration 2)
        - it has no children that can be expanded (marked with +)
        -- will continue to iterate until reached number of iteration (set 10 in the test)
        * nodes in tree will be root, child1, grandchild 1, child2
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child1_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    child2_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1CF"]
    grandchild1_smi = ["N#Cc1cccc(N)c1F", "O=C(Cl)c1ccc(F)cc1"]
    lookup = {
        root_smi: [
            {"smiles": ".".join(child1_smi), "prior": 0.7},
            {"smiles": ".".join(child2_smi), "prior": 0.3},
        ],
        child1_smi[1]: {
            "smiles": ".".join(grandchild1_smi),
            "prior": 0.3,
        },
        grandchild1_smi[1]: {
            "smiles": "",
            "prior": 1.0,
        },
        child2_smi[1]: {
            "smiles": "",
            "prior": 0.3,
        },
    }
    finder = setup_aizynthfinder(
        lookup, [child1_smi[0], child1_smi[2]] + grandchild1_smi
    )
    finder.config.search.iteration_limit = 10

    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 4
    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert (
        state_smiles(nodes[2].state) == [child1_smi[0], child1_smi[2]] + grandchild1_smi
    )
    assert state_smiles(nodes[3].state) == child2_smi
    assert finder.search_stats["iterations"] == 10


def test_two_expansions_cyclic(setup_aizynthfinder):
    """
    Test the building of this tree:
                root
                  |
                child 1
                  |
                child 2
    But making child 2 should be rejected because child 2 == root
    """
    root_smi = "COc1cc2cc(-c3ccc(OC(C)=O)c(OC(C)=O)c3)[n+](C)c(C)c2cc1OC"
    child1_smi = ["COc1cc2cc(-c3ccc(O)c(OC(C)=O)c3)[n+](C)c(C)c2cc1OC"]
    lookup = {
        root_smi: {"smiles": child1_smi[0], "prior": 0.1},
        child1_smi[0]: {
            "smiles": root_smi,
            "prior": 1.0,
        },
    }
    finder = setup_aizynthfinder(lookup, [])
    finder.config.search.iteration_limit = 1

    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 2
    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert finder.search_stats["iterations"] == 1


def test_two_expansions_prune_cyclic(setup_aizynthfinder):
    """
    Test the building of this tree:
                root
                  |
                child 1
                  |
                child 2
    Child 2 will not be rejected, but the tree search will not end, so it will
    continue to expand until reaching maximum depth
    """
    root_smi = "COc1cc2cc(-c3ccc(OC(C)=O)c(OC(C)=O)c3)[n+](C)c(C)c2cc1OC"
    child1_smi = ["COc1cc2cc(-c3ccc(O)c(OC(C)=O)c3)[n+](C)c(C)c2cc1OC"]
    lookup = {
        root_smi: {"smiles": child1_smi[0], "prior": 0.1},
        child1_smi[0]: {
            "smiles": root_smi,
            "prior": 1.0,
        },
    }
    finder = setup_aizynthfinder(lookup, [])
    finder.config.search.iteration_limit = 1
    finder.config.search.algorithm_config["prune_cycles_in_search"] = False

    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 7
    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert state_smiles(nodes[2].state) == [root_smi]
    assert finder.search_stats["iterations"] == 1


def test_two_expansions_two_children_one_filtered(setup_aizynthfinder, caplog):
    """
    Test the building of this tree:
                root
            /           \
        child 1        child 2 (*)
            |             |
        grandchild 1   grandchild 2
    child 2 will not be created as that reaction is filtered away
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child1_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    child2_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F"]
    grandchild_smi = ["N#Cc1cccc(N)c1F", "O=C(Cl)c1ccc(F)cc1"]
    lookup = {
        root_smi: [
            {"smiles": ".".join(child1_smi), "prior": 0.7},
            {"smiles": ".".join(child2_smi), "prior": 0.3},
        ],
        child1_smi[1]: {"smiles": ".".join(grandchild_smi), "prior": 0.7},
        child2_smi[1]: {"smiles": ".".join(grandchild_smi), "prior": 0.7},
    }
    finder = setup_aizynthfinder(
        lookup, [child1_smi[0], child1_smi[2]] + grandchild_smi
    )
    finder.filter_policy[finder.filter_policy.selection[0]].lookup = {
        f"{root_smi}>>{'.'.join(child2_smi)}": 0.2
    }
    finder.config.search.iteration_limit = 10

    with caplog.at_level(logging.DEBUG):
        finder.tree_search()

    assert not any(
        rec.message.startswith("Reject retro reaction") for rec in caplog.records
    )
    nodes = list(finder.tree.graph())
    assert len(nodes) == 5
    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert (
        state_smiles(nodes[2].state) == [child1_smi[0], child1_smi[2]] + grandchild_smi
    )
    assert state_smiles(nodes[3].state) == child2_smi
    assert state_smiles(nodes[4].state) == [child2_smi[0]] + grandchild_smi
    assert finder.search_stats["iterations"] == 10

    # Now raise the filter threshold to remove child 2, grandchild 2
    finder.config.filter_policy["dummy"].filter_cutoff = 0.5
    finder.target_smiles = finder.target_smiles  # Trigger re-set

    with caplog.at_level(logging.DEBUG):
        finder.tree_search()

    assert any(
        rec.message.startswith("Reject retro reaction") for rec in caplog.records
    )
    nodes = list(finder.tree.graph())
    assert len(nodes) == 3
    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert (
        state_smiles(nodes[2].state) == [child1_smi[0], child1_smi[2]] + grandchild_smi
    )
    assert finder.search_stats["iterations"] == 10


def test_stock_info(setup_aizynthfinder):
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child1_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    lookup = {root_smi: {"smiles": ".".join(child1_smi), "prior": 1.0}}
    finder = setup_aizynthfinder(lookup, child1_smi)

    # Test first with return_first
    finder.config.return_first = True
    finder.config.scorers.create_default_scorers()
    finder.tree_search()

    assert finder.stock_info() == {}

    finder.build_routes()

    expected = {smi: ["stock"] for smi in child1_smi}
    expected[root_smi] = []
    assert finder.stock_info() == expected


def test_two_expansions_two_children_full_redundant_expansion(setup_aizynthfinder):
    """
    Test the building of this tree:
                root
            /           \
        child 1        (child 2)
            |             |
        grandchild 1   (grandchild 2)
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    grandchild_smi = ["N#Cc1cccc(N)c1F", "O=C(Cl)c1ccc(F)cc1"]
    lookup = {
        root_smi: [
            {"smiles": ".".join(child_smi), "prior": 0.7},
            {"smiles": ".".join(child_smi), "prior": 0.3},
        ],
        child_smi[1]: {"smiles": ".".join(grandchild_smi), "prior": 0.7},
        child_smi[1]: {"smiles": ".".join(grandchild_smi), "prior": 0.7},
    }
    finder = setup_aizynthfinder(lookup, [child_smi[0], child_smi[2]] + grandchild_smi)

    finder.config.search.algorithm_config["mcts_grouping"] = "full"
    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 3

    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child_smi
    assert state_smiles(nodes[2].state) == [child_smi[0], child_smi[2]] + grandchild_smi
    assert "additional_actions" in nodes[0].children_view()["actions"][0].metadata
    additional_expansions = (
        nodes[0].children_view()["actions"][0].metadata["additional_actions"]
    )
    assert len(additional_expansions) == 1
    assert additional_expansions[0] == {"policy_name": "simple_expansion"}
    assert finder.search_stats["iterations"] == 100

    # Switch to partial degeneracy grouping

    finder.config.mcts_grouping = "partial"
    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 3


def test_two_expansions_two_children_partial_redundant_expansion(setup_aizynthfinder):
    """
    Test the building of this tree:
                root
            /           \
        child 1        (child 2)
            |             |
        grandchild 1   (grandchild 2)
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    child2_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F"]
    grandchild_smi = ["N#Cc1cccc(N)c1F", "O=C(Cl)c1ccc(F)cc1"]
    lookup = {
        root_smi: [
            {"smiles": ".".join(child_smi), "prior": 0.7},
            {"smiles": ".".join(child2_smi), "prior": 0.3},
        ],
        child_smi[1]: {"smiles": ".".join(grandchild_smi), "prior": 0.7},
        child_smi[1]: {"smiles": ".".join(grandchild_smi), "prior": 0.7},
    }
    finder = setup_aizynthfinder(lookup, [child_smi[0], child_smi[2]] + grandchild_smi)

    # First run with full degeneracy grouping

    finder.config.search.algorithm_config["mcts_grouping"] = "full"
    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 5

    # Then turn to partial

    finder.config.search.algorithm_config["mcts_grouping"] = "Partial"
    finder.target_smiles = finder.target_smiles  # Trigger re-set
    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 3

    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child_smi
    assert state_smiles(nodes[2].state) == [child_smi[0], child_smi[2]] + grandchild_smi
    assert "additional_actions" in nodes[0].children_view()["actions"][0].metadata
    additional_expansions = (
        nodes[0].children_view()["actions"][0].metadata["additional_actions"]
    )
    assert len(additional_expansions) == 1
    assert additional_expansions[0] == {"policy_name": "simple_expansion"}
    assert finder.search_stats["iterations"] == 100


def test_build_routes_combined_scorer(setup_aizynthfinder, shared_datadir):
    root_smi = "CN1CCC(C(=O)c2cccc([NH:1][C:2](=O)c3ccc(F)cc3)c2F)CC1"

    reaction_template = pd.read_csv(
        shared_datadir / "test_reactions_template.csv", sep="\t"
    )
    template1_smarts = reaction_template["RetroTemplate"][0]
    template2_smarts = reaction_template["RetroTemplate"][1]

    child1_smi = ["N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "CN1CCC(Cl)CC1", "O"]
    child2_smi = ["N#Cc1cccc(N)c1F", "O=C(Cl)c1ccc(F)cc1"]

    lookup = {
        root_smi: {"smarts": template1_smarts, "prior": 1.0},
        child1_smi[0]: {
            "smarts": template2_smarts,
            "prior": 1.0,
        },
    }

    config_dict = {
        "search": {"break_bonds": [(1, 2)]},
        "post_processing": {
            "route_scorers": ["state score", "broken bonds"],
            "scorer_weights": [1, 1],
        },
    }
    finder = setup_aizynthfinder(
        lookup, [child1_smi[1], child1_smi[2]] + child2_smi, config_dict
    )

    finder.tree_search()
    finder.build_routes()

    score = finder.analysis.sort()[1][0]["state score + broken bonds"]
    assert round(score, 4) == 0.747


def test_one_expansion_multistep(setup_aizynthfinder):
    """
    Test the building of this tree:
                root
                  |
                child 1
    """
    root_smi = "CN1CCC(C(=O)c2cccc(NC(=O)c3ccc(F)cc3)c2F)CC1"
    child1_smi = ["CN1CCC(Cl)CC1", "N#Cc1cccc(NC(=O)c2ccc(F)cc2)c1F", "O"]
    lookup = {root_smi: {"smiles": ".".join(child1_smi), "prior": 1.0}}
    finder = setup_aizynthfinder(lookup, child1_smi)
    finder.config.search.algorithm_config["search_rewards"] = [
        "number of reactions",
        "number of pre-cursors in stock",
    ]

    finder.config.search.return_first = True
    finder.tree_search()

    nodes = list(finder.tree.graph())
    assert len(nodes) == 2
    assert state_smiles(nodes[0].state) == [root_smi]
    assert state_smiles(nodes[1].state) == child1_smi
    assert nodes[0].created_at_iteration == 0
    assert nodes[1].created_at_iteration == 1
    assert finder.search_stats["iterations"] == 1
    assert finder.search_stats["returned_first"]
