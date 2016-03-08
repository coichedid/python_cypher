# -*- coding: utf-8 -*-
"""
This script contains the ``CypherParserBaseClass``, which provides the basic
functionality to parse Cypher queries and run them against graphs.
"""

import itertools
import networkx as nx
import copy
import hashlib
import random
import time
from cypher_tokenizer import *
from cypher_parser import *

PRINT_TOKENS = False
PRINT_MATCHING_ASSIGNMENTS = False


class CypherParserBaseClass(object):
    """The base class that specific parsers will inherit from. Certain methods
       must be defined in the child class. See the docs."""
    def __init__(self):
        self.tokenizer = cypher_tokenizer
        self.parser = cypher_parser

    def parse(self, query):
        """Calls yacc to parse the query string into an AST."""
        self.tokenizer.input(query)
        tok = self.tokenizer.token()
        while tok:
            if PRINT_TOKENS:
                print tok
            tok = self.tokenizer.token()
        return self.parser.parse(query)

    def query(self, graph_object, query_string):
        """Top-level function that's called by the parser when a query has
           been transformed to its AST. This function routes the parsed
           query to a smal number of high-level functions for handling
           specific types of queries (e.g. MATCH, CREATE, ...)"""
        parsed_query = self.parse(query_string)
        if isinstance(parsed_query, MatchWhereReturnQuery):
            for match in self.matching_nodes(graph_object, parsed_query):
                yield match
        elif isinstance(parsed_query, CreateReturnQuery):
            self.create_query(graph_object, parsed_query)
        else:
            raise Exception("Unhandled case in query function.")

    def create_query(self, graph_object, parsed_query):
        """For executing queries of the form CREATE... RETURN."""
        atomic_facts = extract_atomic_facts(parsed_query)
        designation_to_node = {}
        designation_to_edge = {}
        for literal in parsed_query.create_clause.literals.literal_list:
            designation_to_node[literal.designation] = self._create_node(
                graph_object, literal.node_class,
                **literal.attribute_conditions)
        for edge_fact in [
                fact for fact in atomic_facts if
                isinstance(fact, EdgeExists)]:
            source_node = designation_to_node[edge_fact.node_1]
            target_node = designation_to_node[edge_fact.node_2]
            edge_label = edge_fact.edge_label
            new_edge_id = self._create_edge(graph_object, source_node,
                                            target_node, edge_label=edge_label)
            designation_to_edge['placeholder'] = new_edge_id

    def matching_nodes(self, graph_object, parsed_query):
        """For executing queries of the form MATCH... [WHERE...] RETURN..."""

        def _eval_constraint(constraint):
            """This is the basis case for the recursive check
               on WHERE clauses."""
            value = self._attribute_value_from_node_keypath(
                self._get_node(
                    graph_object,
                    var_to_element[constraint.keypath[0]]),
                constraint.keypath[1:])
            return value == constraint.value

        def _eval_boolean(clause):
            """Recursive function to evaluate WHERE clauses. ``Or``
               and ``Not`` classes inherit from ``Constraint``."""
            if isinstance(clause, Or):
                return (_eval_boolean(clause.left_disjunct) or
                        _eval_boolean(clause.right_disjunct))
            elif isinstance(clause, Not):
                return not _eval_boolean(clause.argument)
            elif isinstance(clause, Constraint):
                return _eval_constraint(clause)

        all_designations = set()
        # Track down atomic_facts from outer scope.
        atomic_facts = extract_atomic_facts(parsed_query)
        for fact in atomic_facts:
            if hasattr(fact, 'designation') and fact.designation is not None:
                all_designations.add(fact.designation)
        all_designations = sorted(list(all_designations))

        domain = self._get_domain(graph_object)
        for domain_assignment in itertools.product(
                *[domain] * len(all_designations)):
            var_to_element = {all_designations[index]: element for index,
                              element in enumerate(domain_assignment)}
            # Not sure if element_to_var will be useful
            # element_to_var = {
            #     v: k for k, v in var_to_element.iteritems()}
            # print 'checking assignment:', var_to_element
            sentinal = True
            for atomic_fact in atomic_facts:
                if isinstance(atomic_fact, ClassIs):
                    var_class = self._node_class(
                        self._get_node(graph_object,
                                       var_to_element[
                                           atomic_fact.designation]))
                    # var = atomic_fact.designation
                    desired_class = atomic_fact.class_name
                    if desired_class is not None and var_class != desired_class:
                        sentinal = False
                elif isinstance(atomic_fact, EdgeExists):
                    if not any((self._edge_class(connecting_edge) ==
                                atomic_fact.edge_label)
                               for _, connecting_edge in
                               self._edges_connecting_nodes(
                                   graph_object,
                                   var_to_element[atomic_fact.node_1],
                                   var_to_element[atomic_fact.node_2])):
                        sentinal = False
                elif isinstance(atomic_fact, WhereClause):

                    sentinal = sentinal & _eval_boolean(atomic_fact.constraint)

            if sentinal:
                if PRINT_MATCHING_ASSIGNMENTS:
                    print var_to_element  # For debugging purposes only
                variables_to_return = (
                    parsed_query.return_variables.variable_list)
                return_list = []
                for return_path in variables_to_return:
                    if isinstance(return_path, str):
                        return_list.append(var_to_element[return_path])
                        break
                    node = self._get_node(
                        graph_object, var_to_element[return_path.pop(0)])
                    return_list.append(
                        self._node_attribute_value(node, return_path))
                yield return_list

    def _get_domain(self, *args, **kwargs):
        raise NotImplementedError(
            "Method _get_domain needs to be defined in child class.")

    def _get_node(self, *args, **kwargs):
        raise NotImplementedError(
            "Method _get_domain needs to be defined in child class.")
        
    def _node_attribute_value(self, *args, **kwargs):
        raise NotImplementedError(
            "Method _get_domain needs to be defined in child class.")

    def _edge_exists(self, *args, **kwargs):
        raise NotImplementedError(
            "Method _edge_exists needs to be defined in child class.")

    def _edges_connecting_nodes(self, *args, **kwargs):
        raise NotImplementedError(
            "Method _edges_connecting_nodes needs to be defined "
            "in child class.")

    def _node_class(self, *args, **kwargs):
        raise NotImplementedError(
            "Method _node_class needs to be defined in child class.")

    def _edge_class(self, *args, **kwargs):
        raise NotImplementedError(
            "Method _edge_class needs to be defined in child class.")

    def _create_node(self, *args, **kwargs):
        raise NotImplementedError(
            "Method _create_node needs to be defined in child class.")

    def _create_edge(self, *args, **kwargs):
        raise NotImplementedError(
            "Method _create_edge needs to be defined in child class.")

    def _attribute_value_from_node_keypath(self, *args, **kwargs):
        raise NotImplementedError(
            "Method _attribute_value_from_node_keypath needs to be defined.")


class CypherToNetworkx(CypherParserBaseClass):
    """Child class inheriting from ``CypherParserBaseClass`` to hook up
       Cypher functionality to NetworkX.
    """
    def _get_domain(self, obj):
        return obj.nodes()

    def _get_node(self, graph_object, node_name):
        return graph_object.node[node_name]

    def _node_attribute_value(self, node, attribute_list):
        out = copy.deepcopy(node)
        for attribute in attribute_list:
            try:
                out = out.get(attribute)
            except:
                raise Exception(
                    "Asked for non-existent attribute {} in node {}.".format(
                        attribute, node))
        return out

    def _attribute_value_from_node_keypath(self, node, keypath):
        value = node
        for key in keypath:
            try:
                value = value[key]
            except (KeyError, TypeError,):
                return None
        return value

    def _edge_exists(self, graph_obj, source, target,
                     edge_class=None, directed=True):
        raise NotImplementedError("Haven't finished _edge_exists.")

    def _edges_connecting_nodes(self, graph_object, source, target):
        try:
            for index, data in graph_object.edge[source][target].iteritems():
                yield index, data
        except:
            pass

    def _node_class(self, node, class_key='class'):
        return node.get(class_key, None)

    def _edge_class(self, edge, class_key='class'):
        try:
            out = edge.get(class_key, None)
        except AttributeError:
            out = None
        return out

    def _create_node(self, graph_object, node_class, **attribute_conditions):
        """Create a node and return it so it can be referred to later."""
        new_id = unique_id()
        attribute_conditions['class'] = node_class
        graph_object.add_node(new_id, **attribute_conditions)
        return new_id

    def _create_edge(self, graph_object, source_node,
                     target_node, edge_label=None):
        new_edge_id = unique_id()
        graph_object.add_edge(
            source_node, target_node,
            **{'edge_label': edge_label, '_id': new_edge_id})
        return new_edge_id


def random_hash():
    """Return a random hash for naming new nods and edges."""
    random_hash = hashlib.md5(str(random.random() + time.time())).hexdigest()
    return random_hash


def unique_id():
    """Call ``random_hash`` and prepend ``_id_`` to it."""
    return '_id_' + random_hash()


def extract_atomic_facts(query):
    my_parser = CypherToNetworkx()
    if isinstance(query, str):
        query = my_parser.parse(query)

    def _recurse(subquery):
        if subquery is None:
            return
        elif isinstance(subquery, MatchWhereReturnQuery):
            _recurse(subquery.match_clause)
            _recurse(subquery.where_clause)
        elif isinstance(subquery, MatchQuery):
            _recurse(subquery.literals)
            _recurse(subquery.where_clause)
        elif isinstance(subquery, CreateClause):
            _recurse(subquery.literals)
        elif isinstance(subquery, Literals):
            for literal in subquery.literal_list:
                _recurse(literal)
        elif isinstance(subquery, Node):
            if (not hasattr(subquery, 'designation') or
                    subquery.designation is None):
                subquery.designation = (
                    '_v' + str(_recurse.next_anonymous_variable))
                subquery.next_anonymous_variable += 1
            _recurse.atomic_facts.append(ClassIs(subquery.designation,
                                                 subquery.node_class))
            _recurse.atomic_facts += subquery.connecting_edges
            if hasattr(subquery, 'attribute_conditions'):
                _recurse.atomic_facts.append(
                    NodeHasDocument(
                        designation=subquery.designation,
                        document=(subquery.attribute_conditions if
                                  len(subquery.attribute_conditions) > 0
                                  else None)))
            if hasattr(subquery, 'foobarthingy'):
                pass
        elif isinstance(subquery, WhereClause):
            _recurse.atomic_facts.append(subquery)
        elif isinstance(subquery, CreateReturnQuery):
            _recurse(subquery.create_clause)
        else:
            raise Exception('unhandled case in extract_atomic_facts:' + (
                subquery.__class__.__name__))
    _recurse.atomic_facts = []
    _recurse.next_anonymous_variable = 0
    _recurse(query)
    return _recurse.atomic_facts


def main():
    # sample = ','.join(['MATCH (x:SOMECLASS {bar : "baz"',
    #                    'foo:"goo"})<-[:WHATEVER]-(:ANOTHERCLASS)',
    #                    '(y:LASTCLASS) RETURN x.foo, y'])

    create = 'CREATE (n:SOMECLASS {foo: "bar", bar: {qux: "baz"}})-[e:EDGECLASS]->(m:ANOTHERCLASS) RETURN n'
    create_query = 'CREATE (n:SOMECLASS {foo: "bar", bar: {qux: "thing"}})-->(m:ANOTHERCLASS) RETURN n'
    test_query = 'MATCH (n:SOMECLASS)-->(m:ANOTHERCLASS) WHERE n.foo = "bar" RETURN n.bar.qux'
    atomic_facts = extract_atomic_facts(test_query)
    g = nx.MultiDiGraph()
    my_parser = CypherToNetworkx()
    for i in my_parser.query(g, create_query):
        pass  # a generator, we need to loop over results to run.
    for i in my_parser.query(g, test_query):
        print i  # also a generator
    import pdb; pdb.set_trace()
    return atomic_facts


if __name__ == '__main__':
    # This main method is just for testing
    out = main()

