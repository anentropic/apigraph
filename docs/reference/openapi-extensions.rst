.. contents:: Contents:
   :backlinks: none 

Extensions to OpenAPI
=====================

OpenAPI v3.0 provides only rudimentary support for `defining links`_ between documents. Specifically you can define a forward-pointing link which can extract values from the origin operation (e.g. from the request querystring, or response body) and pass them as request parameters to the destination operation.

For **Apigraph** we want to be able to *completely specify* the dependency relationship between API endpoints, across multiple interconnected APIs. Additionally, and importantly, we want to be able to take a *leaf* in the graph and trace back up its branches to the root request(s). In other words to extract all the prerequsites for any request.

For our use case we encountered three problems with OpenAPI 3.0 Links specification:

1. There is no way to use extracted values in the destination operation's request body, except as the *whole* ``requestBody``. For example you cannot take a value from the response body and use it as a *field* in the request body of the downstream request. This is due to limitations in the definition of `request parameters`_ - they can only address locations like the querystring or headers. We are not the first to notice this problem, there is an `open issue here`_ where we have proposed our extension format.
2. The current forward-pointing link structure means that origin operations need to know of, and specify, all of their downstream dependents. Realistically that is only suited to the same-document use case. If you imagine the scenario of an organisation using microservices, where each service is managed by a different team, then you will find it inconvenient to define links in this way. It means you have to rely on a different team to specify *your* dependency requirement in the OpenAPI doc *they* are responsible for. In the case where your API has a dependency on a 3rd-party API then it becomes impossible. Instead we propose `an alternative backward-pointing link specification`_ ("backlinks") that allows downstream services to fully specify their upstream dependencies.
3. There can be multiple paths through the graph, i.e. multiple links or backlinks pointing to any one Operation. We would like a way to distinguish these paths so that Apigraph can select *a particular unique path* through the graph. Since "path" already has a meaning in OpenAPI we will call these paths "chains" (as in links-in-a-chain). Below we propose extensions which allow links and require backlinks to specify a named chain-id which they belong to.

.. _defining links: https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.2.md#linkObject
.. _request parameters: https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.2.md#parameterObject
.. _open issue here: https://github.com/OAI/OpenAPI-Specification/issues/1594#issuecomment-641629537
.. _an alternative backward-pointing link specification: https://github.com/OAI/OpenAPI-Specification/issues/2196


``x-apigraph-requestBodyParameters``
------------------------------------

This is an extension to the `Link Object`_.

================================  =================================  ===========
Field Name                        Type                               Description
================================  =================================  ===========
x-apigraph-requestBodyParameters  Map[{JSON Pointer}, {expression}]  The keys are `JSON Pointers`_ identifying locations in the target request body. The values are `runtime expressions`_ to extract values from the source Operation.
================================  =================================  ===========

**Example**

.. code-block:: yaml
   :emphasize-lines: 10,11

	paths:
	  '/':
	     get:
	       responses:
	         '200':
	            description: ok
	            links:
	              submitLink:
	                operationId: postSubmit
	                x-apigraph-requestBodyParameters:
	                  /foo: $response.body#/foo
	  '/submit':
	    post:
	      operationId: postSubmit

Here we have an operation ``GET /`` and its ``200`` status response defines a forward-pointing link to the ``postSubmit`` operation id (``POST /submit``). The link itself has a name, ``submitLink``. So far this is all basic OpenAPI 3.0 stuff.

Under the Link Object we have our extension field ``x-apigraph-requestBodyParameters``, which here defines a single link parameter.

The key of the parameter ``/foo`` is a JSON Pointer which selects a unique location in the link target's request body.

The value of the parameter ``$response.body#/foo`` is a runtime expression which selects a value from the link source, exactly as used elsewhere in the OpenAPI spec - here there is also a JSON Pointer ``/foo``, selecting that value from the response body of the source request.

(see also: `x-apigraph-chainId`_ below)


``x-apigraph-backlinks``
------------------------

This is an extension to the `Operation Object`_.

Our aim is to fully specify all of the *upstream* dependencies of the current operation, i.e. its prerequisite requests.

Conceptually it is similar to the ``links`` field in a `Response Object`_ and the structure is deliberately similar.

=====================  =========================================================  ===========
Field Name             Type                                                       Description
=====================  =========================================================  ===========
x-apigraph-backlinks   Map[``string``, `Backlink Object`_ | `Reference Object`_]  A mapping of names to Backlink objects.
=====================  =========================================================  ===========


Backlink Object
~~~~~~~~~~~~~~~

OpenAPI 3.0 Links go from ``Response -> Operation (downstream)``.

Backlinks are the reverse, ``Operation -> Response (upstream)``.

So here we identify a specific Response in an upstream Operation and select values from that Response, for use in the backlink's parent Operation.

We must recognise that there can be multiple upstream paths which can lead to the target Operation, which our backlinks are defined on. We shall call these paths "chains" (as in links-in-a-chain, since "path" already has a meaning in OpenAPI spec).

The links and backlinks in each chain will be unified by means of their ``chainId``, an arbitrarily chosen string name. Links and backlinks which do not specify an explicity chain-id will implicitly belong to the chain-id ``default``.

There may be multiple backlinked operations required by the current operation. We might imagine these as operations which could be made in parallel, where all of them are necessary prerequisites of the current request. In that case they MUST share the same chain-id. Otherwise, optional prerequisites should be given distinct chain-ids.

NOTE: we only ever specify the *immediate ancestors* of the current request. Do not confuse these parallel prerequisites for "grandparent" operations (i.e. they are not serial prerequisites-of-prerequisites).

We then extract the necessary values from these prerequisite operations, for use when making a request to the backlink's parent Operation.

**Fixed Fields**

=====================  =================================  ===========
Field Name             Type                               Description
=====================  =================================  ===========
chainId                ``string``                         The chain-id to which this Backlink object belongs. If not present then the Backlink implicitly belongs to the ``null`` chain-id.
responseRef            ``string``                         A `JSON Reference`_ identifying a specific Response in the target Operation. **One of** ``responseRef`` or ``operationRef`` or ``operationId`` is **REQUIRED**.
operationRef           ``string``                         A `JSON Reference`_ identifying a specific Operation. **One of** ``responseRef`` or ``operationRef`` or ``operationId`` is **REQUIRED**.
operationId            ``string``                         Name identifying a specific Operation in the current document. **One of** ``responseRef`` or ``operationRef`` or ``operationId`` is **REQUIRED**.
response               ``string``                         Name identifying to a specific response in the otherwise specified Operation. **REQUIRED** if either ``operationRef`` or ``operationId`` are used and mutally exclusive of ``responseRef`` field.
parameters             Map[``string``, {expression}]      A mapping of parameter names (from the backlink's parent operation) to `runtime expressions`_ to extract a value from the upstream Response which is the target of this backlink.
requestBodyParameters  Map[{JSON Pointer}, {expression}]  A mapping of `JSON Pointers`_ (identifying values in the backlink's parent Operation's request body) to `runtime expressions`_ to extract a value from the upstream Response which is the target of this backlink.
requestBody            {expression}                       A `runtime expression`_ to extract a value from the upstream Response it and use as the request body of the current Operation.
description	           ``string``                         A description of the link. `CommonMark syntax`_ MAY be used for rich text representation.
server	               `Server Object`_                   A server object to be used by the target operation.
=====================  =================================  ===========

The ``chainId`` field serves the same purpose for backlinks as the `x-apigraph-chainId`_ extension field does for forward-pointing links. **IMPORTANT NOTE:** if there are multiple backlinks from the same Operation and having the same ``chainId`` (which will be ``null`` if not specified) then they are all considered *required prerequisites* to that Operation, when traversing that particular chain with Apigraph.

The ``requestBodyParameters`` field serves the same purpose for backlinks as the `x-apigraph-requestBodyParameters`_ extension field does for forward-pointing links.

The ``requestBody`` field serves the same purpose for backlinks as the existing one for `Link Object`_.

``description`` and ``server`` are also as per `Link Object`_.


**Complete Example**

.. code-block:: yaml
   :emphasize-lines: 47-60

	openapi: 3.0.0
	info: 
	  title: Backlinks Example
	  version: 1.0.0
	paths:
	  /1.0/users/{username}: 
	    get: 
	      operationId: getUserByNamev1
	      parameters: 
	      - name: username
	        in: path
	        required: true
	        schema:
	          type: string
	      responses: 
	        '200':
	          description: The User
	          content:
	            application/json:
	              schema: 
	                $ref: '#/components/schemas/user'
	  /2.0/users/{username}: 
	    get: 
	      operationId: getUserByName
	      parameters: 
	      - name: username
	        in: path
	        required: true
	        schema:
	          type: string
	      responses: 
	        '200':
	          description: The User
	          content:
	            application/json:
	              schema: 
	                $ref: '#/components/schemas/user'
	  /repositories/{username}:
	    get:
	      operationId: getRepositoriesByOwner
	      parameters:
	        - name: username
	          in: path
	          required: true
	          schema:
	            type: string
	      x-apigraph-backlinks:
	        Get User by Username:
	          chainId: default
	          operationId: getUserByName
	          response: "200"
	          parameters:
  	            # parameter name in the parent Operation: value selector
	            username: $response.body#/username
	        Get User by Username v1:
	          chainId: v1
	          operationId: getUserByNamev1
	          response: "200"
	          parameters:
	            username: $response.body#/username
	      responses:
	        '200':
	          description: repositories owned by the supplied user
	          content: 
	            application/json:
	              schema:
	                type: array
	                items:
	                  $ref: '#/components/schemas/repository'
	components:
	  schemas: 
	    user: 
	      type: object
	      properties: 
	        username: 
	          type: string
	        uuid: 
	          type: string
	    repository: 
	      type: object
	      properties: 
	        slug: 
	          type: string
	        owner: 
	          $ref: '#/components/schemas/user'

Here there are two chains; ``default`` and ``v1``.

This highlights one use-case for named link chains - in a versioned API you will have redundant links to any un-versioned parts of the API (or to other APIs which are on a different versioning schedule).

In Apigraph we want to be able to say, for the ``GET /repositories/{username}`` operation, *"give me all the prerequisite operations in the v1 chain for this endpoint"*.


``x-apigraph-chainId``
-----------------------

This is an extension to the `Link Object`_.

For Apigraph's purposes, if the Link does not have an ``x-apigraph-chainId`` field then it belongs to the ``null`` chain-id.

**Fixed Fields**

===================  ==========  ===========
Field Name           Type        Description
===================  ==========  ===========
x-apigraph-chainId  ``string``  The chain-id to which this `Link Object`_ belongs.
===================  ==========  ===========

**Example**

.. code-block:: yaml
   :emphasize-lines: 10

	paths:
	  '/':
	     get:
	       responses:
	         '200':
	            description: ok
	            links:
	              submitLink:
	                operationId: postSubmit
	                x-apigraph-chainId: default
	  '/submit':
	    post:
	      operationId: postSubmit


.. _Link Object: https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.2.md#linkObject
.. _Operation Object: https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.2.md#operationObject
.. _Reference Object: https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.2.md#referenceObject
.. _Response Object: https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.2.md#responseObject
.. _Server Object: https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.2.md#serverObject
.. _JSON Pointer: https://tools.ietf.org/html/rfc6901
.. _JSON Pointers: https://tools.ietf.org/html/rfc6901
.. _JSON Reference: https://tools.ietf.org/html/draft-pbryan-zyp-json-ref-03
.. _runtime expression: https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.2.md#runtimeExpression
.. _runtime expressions: https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.2.md#runtimeExpression
.. _CommonMark syntax: http://spec.commonmark.org/
