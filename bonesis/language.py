
__language_api__ = {}

def language_api(cls):
    __language_api__[cls.__name__] = cls
    return cls

class ManagedIface(object):
    def __init__(self, manager):
        self.manager = manager
        self.recovery = {}
        def managed(cls):
            class Managed(cls):
                iface = self
                mgr = self.manager
            Managed.__name__ = cls.__name__
            return Managed
        for name, cls in __language_api__.items():
            setattr(self, name, managed(cls))

    def install(self, scope):
        sid = id(scope)
        is_dict = isinstance(scope, dict)
        rec = self.recovery[sid] = {}
        for k in __language_api__:
            hasv = (k in scope) if is_dict else hasattr(scope, k)
            if hasv:
                rec[k] = scope[k] if is_dict else getattr(scope, k)
            cls = getattr(self, k)
            setv = scope.__setitem__ if is_dict else scope.__setattr__
            setv(k, getattr(self, k))

    def uninstall(self, scope):
        sid = id(scope)
        is_dict = isinstance(scope, dict)
        rec = self.recovery[sid]
        for k in __language_api__:
            if k in rec:
                setv = scope.__setitem__ if is_dict else scope.__setattr__
                setv(k, rec[k])
            else:
                delv = scope.__delitem__ if is_dict else scope.__delattr__
                delv(k)
        del self.recovery[sid]


@language_api
class mutant(object):
    def __init__(self, mutations):
        self.mutations = mutations
    def __enter__(self):
        return ManagedIface(self.mgr.mutant_context(self.mutations))
    def __exit__(self, *args):
        pass

def declare_operator(operator):
    def decorator(func):
        def wrapper(K):
            setattr(K, operator, func)
            return K
        return wrapper
    return decorator

@declare_operator("__ge__") # >=
def reach_operator(left, right):
    return left.iface.reach(left, right)

@declare_operator("__rshift__") # >>
def allreach_operator(left, right):
    return left.iface.allreach(left, right)

@declare_operator("__truediv__") # /
def nonreach_operator(left, right):
    return left.iface.nonreach(left, right)

@declare_operator("__floordiv__") # //
def final_nonreach_operator(left, right):
    return left.iface.final_nonreach(left, right)

@declare_operator("__ne__") # !=
def different_operator(left, right):
    return left.iface.different(left, right)


class BonesisTerm(object):
    def __init__(self):
        assert hasattr(self, "mgr"), \
                "do not instantiate non-managed class!"
    def _set_iface(self, iface):
        self.iface = iface
        self.mgr = self.iface.manager

    def __ge__(a, b):
        raise TypeError(f"'{a.__class__.__name__}' objects do not support '>=' operator")
    def __rshift__(a, b):
        raise TypeError(f"'{a.__class__.__name__}' objects do not support '>>' operator")
    def __truediv__(a, b):
        raise TypeError(f"'{a.__class__.__name__}' objects do not support '/' operator")
    def __floordiv__(a, b):
        raise TypeError(f"'{a.__class__.__name__}' objects do not support '//' operator")
    def __ne__(a, b):
        raise TypeError(f"'{a.__class__.__name__}' objects do not support '!=' operator")

class BonesisVar(BonesisTerm):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.publish()
    def publish(self):
        pass

@allreach_operator
class ObservationVar(BonesisVar):
    def __init__(self, name):
        super().__init__(name)
    def publish(self):
        self.mgr.register_observation(self)
    def __invert__(self):
        return self.iface.cfg(self.name, obs=self)
    def __pos__(self):
        return self.iface.cfg(None, obs=self)
    def __str__(self):
        return f"Observation({repr(self.name)})"
__language_api__["obs"] = ObservationVar

@different_operator
@reach_operator
@allreach_operator
@nonreach_operator
@final_nonreach_operator
class ConfigurationVar(BonesisVar):
    def __init__(self, name=None, obs=None):
        self.obs = obs
        super().__init__(name)
    def publish(self):
        self.mgr.register_configuration(self)
    def __str__(self):
        return f"Configuration({repr(self.name or id(self))})"
    def __setitem__(self, node, right):
        self.mgr.assert_node_exists(node)
        if isinstance(right, bool):
            right = int(right)
        if isinstance(right, int):
            if not right in [0,1]:
                raise TypeError("cannot assign integers other than 0/1")
            self.mgr.register_predicate("cfg_assign", self, node, right)
        else:
            raise TypeError(f"Invalid type for assignment {type(right)}")
__language_api__["cfg"] = ConfigurationVar

@language_api
class BonesisPredicate(BonesisTerm):
    support_mutations = True
    def __init__(self, *args):
        self.args = args
        if not hasattr(self, "predicate_name"):
            self.predicate_name = self.__class__.__name__
        def auto_iface(obj):
            if isinstance(obj, BonesisTerm):
                if not hasattr(self, "iface"):
                    self._set_iface(obj.iface)
                else:
                    assert obj.iface is self.iface, "mixed managers"
            elif isinstance(obj, (list, set, tuple)):
                [auto_iface(e) for e in obj]
        for obj in self.args:
            auto_iface(obj)
        assert hasattr(self, "mgr"), "Could not find manager"
        if hasattr(self.mgr, "mutations") and not self.support_mutations:
            raise TypeError(f"Cannot use {self.__class__.__name__} in a mutant context")
        super().__init__()
        self.publish()
    @classmethod
    def type_error(celf):
        raise TypeError(f"Invalid arguments for {celf.__name__}")
    def publish(self):
        self.mgr.register_predicate(self.predicate_name, *self.args)
    def left(self):
        return self.args[0]
    def right(self):
        return self.args[-1]
    def __repr__(self):
        return f"{self.__class__.__name__}{tuple(map(repr,self.args))}"

@language_api
class constant(BonesisPredicate):
    def __init__(self, node, value):
        super().__init__(node, value)
        assert node in self.mgr.bo.domain

@language_api
@different_operator
class fixed(BonesisPredicate):
    def __init__(self, arg):
        if isinstance(arg, ConfigurationVar):
            self.predicate_name = "fixpoint"
        elif isinstance(arg, ObservationVar):
            self.predicate_name = "trapspace"
            arg = +arg
        else:
            self.type_error()
        super().__init__(arg)

@language_api
class all_fixpoints(BonesisPredicate):
    _unit_types = (ObservationVar,)
    support_mutations = False
    def __init__(self, arg):
        if isinstance(arg, (set, list, tuple)):
            for e in arg:
                if not isinstance(e, self._unit_types):
                    self.type_error()
        elif isinstance(arg, self._unit_types):
            arg = (arg,)
        else:
            self.type_error()
        super().__init__(arg)
@language_api
class all_attractors(all_fixpoints):
    pass

class _ConfigurableBinaryPredicate(BonesisPredicate):
    def __init__(self, left, right, options=None):
        left = self.left_arg(left)
        self.options = self.default_options if options is None else options
        self.closed = False
        if isinstance(right, str):
            self.options = (right,)
        elif isinstance(right, tuple) and set({type(t) for t in right}) == {str}:
            self.options = right
        else:
            self.closed = True
            right = self.right_arg(right)
        for opt in self.options:
            if opt not in self.supported_options:
                raise TypeError(f"unsupported option '{opt}'")
        super().__init__(left, right)

    def publish(self):
        if not self.closed:
            return
        self.mgr.register_predicate(self.predicate_name, self.options, *self.args)

    def __xor__(self, right):
        return self.__class__(self.left(), right, options=self.options)


@language_api
class allreach(_ConfigurableBinaryPredicate):
    supported_options = {"fixpoints", "attractors_contain"}
    default_options = ("attractors_contain",)
    """
    left: cfg, reach(), obs
    right: obs, set([obs])
    """
    @classmethod
    def left_arg(celf, arg):
        if isinstance(arg, ConfigurationVar):
            return arg
        if isinstance(arg, reach):
            return celf.left_arg(arg.right())
        celf.type_error()
    @classmethod
    def right_arg(celf, arg):
        if isinstance(arg, ObservationVar):
            return {arg}
        elif isinstance(arg, set):
            for elt in arg:
                if not isinstance(elt, ObservationVar):
                    celf.type_error()
            return arg
        celf.type_error()


@reach_operator
@allreach_operator
@nonreach_operator
@final_nonreach_operator
@language_api
class reach(BonesisPredicate):
    """
    left: cfg, reach()
    right: cfg, obs, reach(), fixed()
    """
    def __init__(self, left, right):
        left = self.left_arg(left)
        right = self.right_arg(right)
        super().__init__(left, right)
    @classmethod
    def left_arg(celf, arg):
        if isinstance(arg, ConfigurationVar):
            return arg
        if isinstance(arg, reach):
            return celf.left_arg(arg.right())
        celf.type_error()
    @classmethod
    def right_arg(celf, arg):
        if isinstance(arg, ConfigurationVar):
            return arg
        if isinstance(arg, ObservationVar):
            return celf.right_arg(+arg)
        if isinstance(arg, (fixed, reach)):
            return celf.right_arg(arg.left())
        celf.type_error()


@language_api
class nonreach(reach):
    def __init__(self, left, right):
        if isinstance(right, fixed):
            self.predicate_name = "final_nonreach"
        super().__init__(left, right)
    @classmethod
    def right_arg(celf, arg):
        if isinstance(arg, ObservationVar):
            celf.type_error() # universal constraint
        return super().right_arg(arg)

@language_api
class final_nonreach(nonreach):
    def __init__(self, left, right):
        if not isinstance(right, fixed):
            self.type_error()
        super().__init__(left, right)

@language_api
class different(BonesisPredicate):
    """
    left: cfg, fixed()
    right: cfg, fixed()
    """
    def __init__(self, left, right):
        if isinstance(left, fixed):
            if left.predicate_name != "fixpoint":
                self.type_error()
            left = left.left()
        if isinstance(right, fixed):
            if right.predicate_name != "fixpoint":
                self.type_error()
            right = right.right()
        if not isinstance(left, ConfigurationVar) or \
                not isinstance(right, ConfigurationVar):
            self.type_error()
        super().__init__(left, right)

@language_api
class custom(BonesisPredicate):
    def __init__(self, arg):
        if not isinstance(arg, str):
            self.type_error()
        super().__init__(arg)


class BonesisOptimization(object):
    def __init__(self):
        super().__init__()
        self.publish()
    def publish(self):
        name = self.__class__.__name__
        idx = name.index("_")
        opt = name[:idx]
        name = name[idx+1:]
        self.mgr.append_optimization(opt, name)

@language_api
class maximize_nodes(BonesisOptimization):
    pass
@language_api
class maximize_constants(BonesisOptimization):
    pass
@language_api
class maximize_strong_constants(BonesisOptimization):
    pass
