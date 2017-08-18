from __future__ import division, unicode_literals, print_function

import itertools
from math import pi, fabs
from operator import itemgetter
import warnings

import numpy as np

from pymatgen.analysis.defects.point_defects import \
        ValenceIonicRadiusEvaluator
from pymatgen.analysis.structure_analyzer import OrderParameters
from pymatgen.core.periodic_table import Specie
from pymatgen.core.structure import Element
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from matminer.featurizers.base import BaseFeaturizer

__authors__ = 'Anubhav Jain <ajain@lbl.gov>, Saurabh Bajaj <sbajaj@lbl.gov>, ' \
              'Nils E.R. Zimmerman <nils.e.r.zimmermann@gmail.com>'
# To do:
# - Use local_env-based neighbor finding
#   once this is part of the stable Pymatgen version.

class PackingFraction(BaseFeaturizer):
    """
    Calculates the packing fraction of a crystal structure.
    """

    def __init__(self):
        BaseFeaturizer.__init__(self)

    def featurize(self, s):
        """
        Get packing fraction of the input structure.
        Args:
            s: Pymatgen Structure object.

        Returns:
            f (float): packing fraction.
        """

        if not s.is_ordered:
            raise ValueError("Disordered structure support not built yet.")
        total_rad = 0
        for site in s:
            total_rad += site.specie.atomic_radius ** 3
        return [4 * pi * total_rad / (3 * s.volume)]

    def feature_labels(self):
        return ["Packing fraction"]

    def credits(self):
        return ("")

    def implementors(self):
        return ("Saurabh Bajaj")


class VolumePerSite(BaseFeaturizer):
    """
    Calculates volume per site in a crystal structure.
    """

    def __init__(self):
        BaseFeaturizer.__init__(self)

    def featurize(self, s):
        """
        Get volume per site of the input structure.
        Args:
            s: Pymatgen Structure object.

        Returns:
            f (float): volume per site.
        """
        if not s.is_ordered:
            raise ValueError("Disordered structure support not built yet.")

        return [s.volume / len(s)]

    def feature_labels(self):
        return ["Volume per site"]

    def credits(self):
        return ("")

    def implementors(self):
        return ("Saurabh Bajaj")


class Density(BaseFeaturizer):
    """
    Gets the density of a crystal structure.
    """

    def __init__(self):
        BaseFeaturizer.__init__(self)

    def featurize(self, s):
        """
        Get density of the input structure.
        Args:
            s: Pymatgen Structure object.

        Returns:
            f (float): density.
        """

        return [s.density]

    def feature_labels(self):
        return ["Density"]

    def credits(self):
        return ("")

    def implementors(self):
        return ("Saurabh Bajaj")


class RadialDistributionFunction(BaseFeaturizer):
    """
    Calculate the radial distribution function (RDF) of a crystal
    structure.
    Args:
        cutoff: (float) distance up to which to calculate the RDF.
        bin_size: (float) size of each bin of the (discrete) RDF.
    """

    def __init__(self, cutoff=20.0, bin_size=0.1):
        self.cutoff = cutoff
        self.bin_size = bin_size
        BaseFeaturizer.__init__(self)

    def featurize(self, s):
        """
        Get RDF of the input structure.
        Args:
            s: Pymatgen Structure object.

        Returns:
            rdf, dist: (tuple of arrays) the first element is the
                    normalized RDF, whereas the second element is
                    the inner radius of the RDF bin.
        """
        if not s.is_ordered:
            raise ValueError("Disordered structure support not built yet")
    
        # Get the distances between all atoms
        neighbors_lst = s.get_all_neighbors(self.cutoff)
        all_distances = np.concatenate(
            tuple(map(lambda x: [itemgetter(1)(e) for e in x], neighbors_lst)))
    
        # Compute a histogram
        rdf_dict = {}
        dist_hist, dist_bins = np.histogram(
                all_distances, bins=np.arange(
                0, self.cutoff + self.bin_size, self.bin_size), density=False)
    
        # Normalize counts
        shell_vol = 4.0 / 3.0 * pi * (np.power(
                dist_bins[1:], 3) - np.power(dist_bins[:-1], 3))
        number_density = s.num_sites / s.volume
        rdf = dist_hist / shell_vol / number_density
        return [{'distances': dist_bins[:-1], 'distribution': rdf}]

    def feature_labels(self):
        return ["Radial distribution function"]

    def credits(self):
        return ("")

    def implementors(self):
        return ("Saurabh Bajaj")


class PartialRadialDistributionFunction(BaseFeaturizer):
    """
    Compute the partial radial distribution function (PRDF) of a crystal
    structure, which is the radial distibution function
    broken down for each pair of atom types.  The PRDF was proposed as a
    structural descriptor by [Schutt *et al.*]
    (https://journals.aps.org/prb/abstract/10.1103/PhysRevB.89.205118)
    Args:
        cutoff: (float) distance up to which to calculate the RDF.
        bin_size: (float) size of each bin of the (discrete) RDF.
    """

    def __init__(self, cutoff=20.0, bin_size=0.1):
        BaseFeaturizer.__init__(self)
        self.cutoff = cutoff
        self.bin_size = bin_size

    def featurize(self, s):
        """
        Get PRDF of the input structure.
        Args:
            s: Pymatgen Structure object.

        Returns:
            prdf, dist: (tuple of arrays) the first element is a
                    dictionary where keys are tuples of element
                    names and values are PRDFs.
        """

        if not s.is_ordered:
            raise ValueError("Disordered structure support not built yet")
    
        # Get the composition of the array
        composition = s.composition.fractional_composition.to_reduced_dict
    
        # Get the distances between all atoms
        neighbors_lst = s.get_all_neighbors(self.cutoff)
    
        # Sort neighbors by type
        distances_by_type = {}
        for p in itertools.product(composition.keys(), composition.keys()):
            distances_by_type[p] = []
    
        def get_symbol(site):
            return site.specie.symbol if isinstance(site.specie,
                                                    Element) else site.specie.element.symbol
    
        for site, nlst in zip(s.sites, neighbors_lst):  # Each list is a list for each site
            my_elem = get_symbol(site)
    
            for neighbor in nlst:
                rij = neighbor[1]
                n_elem = get_symbol(neighbor[0])
                # LW 3May17: Any better ideas than appending each element at a time?
                distances_by_type[(my_elem, n_elem)].append(rij)
    
        # Compute and normalize the prdfs
        prdf = {}
        dist_bins = np.arange(0, self.cutoff + self.bin_size, self.bin_size)
        shell_volume = 4.0 / 3.0 * pi * (
                np.power(dist_bins[1:], 3) - np.power(dist_bins[:-1], 3))
        for key, distances in distances_by_type.items():
            # Compute histogram of distances
            dist_hist, dist_bins = np.histogram(distances,
                                                bins=dist_bins, density=False)
            # Normalize
            n_alpha = composition[key[0]] * s.num_sites
            rdf = dist_hist / shell_volume / n_alpha
    
            prdf[key] = {'distances': dist_bins, 'distribution': rdf}

        return [prdf]


    def feature_labels(self):
        return ["Partial radial distribution functions"]

    def credits(self):
        return ("")

    def implementors(self):
        return ("Saurabh Bajaj")


class RadialDistributionFunctionPeaks(BaseFeaturizer):
    """
    Determine the location of the highest peaks in the radial distribution
    function (RDF) of a structure.
    Args:
        n_peaks: (int) number of the top peaks to return .
    """

    def __init__(self, n_peaks=2):
        BaseFeaturizer.__init__(self)
        self.n_peaks = n_peaks

    def featurize(self, rdf):
        """
        Get location of highest peaks in RDF.
    
        Args:
            rdf: (ndarray) RDF as obtained from the
                    RadialDistributionFunction class.
    
        Returns: (ndarray) distances of highest peaks in descending order
                of the peak height
        """
    
        return [[rdf[0]['distances'][i] for i in np.argsort(
                rdf[0]['distribution'])[-self.n_peaks:]][::-1]]

    def feature_labels(self):
        return ["Radial distribution function peaks"]

    def credits(self):
        return ("")

    def implementors(self):
        return ("Saurabh Bajaj")


class ElectronicRadialDistributionFunction(BaseFeaturizer):
    """
    Calculate the crystal structure-inherent
    electronic radial distribution function (ReDF) according to
    Willighagen et al., Acta Cryst., 2005, B61, 29-36.
    The ReDF is a structure-integral RDF (i.e., summed over
    all sites) in which the positions of neighboring sites
    are weighted by electrostatic interactions inferred
    from atomic partial charges. Atomic charges are obtained
    from the ValenceIonicRadiusEvaluator class.
    Args:
        cutoff: (float) distance up to which the ReDF is to be
                calculated (default: longest diagaonal in
                primitive cell).
        dr: (float) width of bins ("x"-axis) of ReDF (default: 0.05 A).
    """

    def __init__(self, cutoff=None, dr=0.05):
        BaseFeaturizer.__init__(self)
        self.cutoff = cutoff
        self.dr = dr

    def featurize(self, s):
        """
        Get ReDF of input structure.

        Args:
            s: input Structure object.

        Returns: (dict) a copy of the electronic radial distribution
                functions (ReDF) as a dictionary. The distance list
                ("x"-axis values of ReDF) can be accessed via key
                'distances'; the ReDF itself is accessible via key
                'redf'.
        """
        if self.dr <= 0:
            raise ValueError("width of bins for ReDF must be >0")
    
        # Make structure primitive.
        struct = SpacegroupAnalyzer(s).find_primitive() or s
    
        # Add oxidation states.
        struct = ValenceIonicRadiusEvaluator(struct).structure
    
        if self.cutoff is None:
            # Set cutoff to longest diagonal.
            a = struct.lattice.matrix[0]
            b = struct.lattice.matrix[1]
            c = struct.lattice.matrix[2]
            self.cutoff = max(
                [np.linalg.norm(a + b + c), np.linalg.norm(-a + b + c),
                 np.linalg.norm(a - b + c), np.linalg.norm(a + b - c)])
    
        nbins = int(self.cutoff / self.dr) + 1
        redf_dict = {"distances": np.array(
                [(i + 0.5) * self.dr for i in range(nbins)]),
                "distribution": np.zeros(nbins, dtype=np.float)}
    
        for site in struct.sites:
            this_charge = float(site.specie.oxi_state)
            neighs_dists = struct.get_neighbors(site, self.cutoff)
            for neigh, dist in neighs_dists:
                neigh_charge = float(neigh.specie.oxi_state)
                bin_index = int(dist / self.dr)
                redf_dict["distribution"][bin_index] += (
                        this_charge * neigh_charge) / (
                        struct.num_sites * dist)
    
        return [redf_dict]

    def feature_labels(self):
        return ["Electronic radial distribution function"]

    def credits(self):
        return ("@article{title={Method for the computational comparison"
                " of crystal structures}, volume={B61}, pages={29-36},"
                " DOI={10.1107/S0108768104028344},"
                " journal={Acta Crystallographica Section B},"
                " author={Willighagen, E. L. and Wehrens, R. and Verwer,"
                " P. and de Gelder R. and Buydens, L. M. C.}, year={2005}}")

    def implementors(self):
        return ("Nils E. R. Zimmermann")


class CoulombMatrix(BaseFeaturizer):
    """
    Generate the Coulomb matrix, M, of the input
    structure (or molecule).  The Coulomb matrix was put forward by
    Rupp et al. (Phys. Rev. Lett. 108, 058301, 2012) and is defined by
    off-diagonal elements M_ij = Z_i*Z_j/|R_i-R_j|
    and diagonal elements 0.5*Z_i^2.4, where Z_i and R_i denote
    the nuclear charge and the position of atom i, respectively.
    """

    def __init__(self):
        BaseFeaturizer.__init__(self)

    def featurize(self, s, diag_elems=False):
        """
        Get Coulomb matrix of input structure.
    
        Args:
            s: input Structure (or Molecule) object.
            diag_elems: (bool) flag indicating whether (True) to use
                    the original definition of the diagonal elements;
                    if set to False (default),
                    the diagonal elements are set to zero.
    
        Returns:
            m: (Nsites x Nsites matrix) Coulomb matrix.
        """
        m = [[] for site in s.sites]
        z = []
        for site in s.sites:
            if isinstance(site, Specie):
                z.append(Element(site.element.symbol).Z)
            else:
                z.append(Element(site.species_string).Z)
        for i in range(s.num_sites):
            for j in range(s.num_sites):
                if i == j:
                    if diag_elems:
                        m[i].append(0.5 * z[i] ** 2.4)
                    else:
                        m[i].append(0)
                else:
                    d = s.get_distance(i, j)
                    m[i].append(z[i] * z[j] / d)
        return np.array(m)

    def feature_labels(self):
        return "Coulomb matrix"

    def credits(self):
        return ("@article{rupp_tkatchenko_muller_vonlilienfeld_2012, title={"
            "Fast and accurate modeling of molecular atomization energies"
            " with machine learning}, volume={108},"
            " DOI={10.1103/PhysRevLett.108.058301}, number={5},"
            " pages={058301}, journal={Physical Review Letters}, author={"
            "Rupp, Matthias and Tkatchenko, Alexandre and M\"uller,"
            " Klaus-Robert and von Lilienfeld, O. Anatole}, year={2012}}")

    def implementors(self):
        return ["Nils E. R. Zimmermann"]


class MinimumRelativeDistances(BaseFeaturizer):
    """
    Determines the relative distance of each site to its closest
    neighbor. We use the relative distance,
    f_ij = r_ij / (r^atom_i + r^atom_j), as a measure rather than the
    absolute distances, r_ij, to account for the fact that different
    atoms/species have different sizes.  The function uses the
    valence-ionic radius estimator implemented in Pymatgen.
    Args:
        cutoff: (float) (absolute) distance up to which tentative
                closest neighbors (on the basis of relative distances)
                are to be determined.
    """

    def __init__(self, cutoff=10.0):
        BaseFeaturizer.__init__(self)
        self.cutoff = cutoff

    def featurize(self, s, cutoff=10.0):
        """
        Get minimum relative distances of all sites of the input structure.
    
        Args:
            s: Pymatgen Structure object.

        Returns:
            min_rel_dists: (list of floats) list of all minimum relative
                    distances (i.e., for all sites).
        """
        vire = ValenceIonicRadiusEvaluator(s)
        min_rel_dists = []
        for site in vire.structure:
            min_rel_dists.append(min([dist / (
                    vire.radii[site.species_string] +
                    vire.radii[neigh.species_string]) for neigh, dist in \
                    vire.structure.get_neighbors(site, self.cutoff)]))
        return [min_rel_dists[:]]

    def feature_labels(self):
        return ["Minimum relative distance of each site"]

    def credits(self):
        return ("")

    def implementors(self):
        return ("Nils E. R. Zimmermann")


class SitesOrderParameters(BaseFeaturizer):
    """
    Calculates all order parameters (OPs) for all sites in a crystal
    structure.
    Args:
        pneighs: (dict) specification and parameters of
                neighbor-finding approach (see
                get_neighbors_of_site_with_index).
    """

    def __init__(self, pneighs=None):
        BaseFeaturizer.__init__(self)
        self.pneighs = pneighs
        self._types = ["cn", "lin"]
        self._labels = ["CN", "q_lin"]
        self._paras = [[], []]
        for i in range(5, 180, 5):
            self._types.append("bent")
            self._labels.append("q_bent_{}".format(i))
            self._paras.append([float(i), 0.0667])
        for t in ["tet", "oct", "bcc", "q2", "q4", "q6", "reg_tri", "sq", \
                "sq_pyr", "tri_bipyr"]:
            self._types.append(t)
            self._labels.append('q_'+t)
            self._paras.append([])

    def featurize(self, s):
        """
        Calculate all sites' local structure order parameters (LSOPs).

        Args:
            s: Pymatgen Structure object.

            Returns:
                opvals: (2D array of floats) LSOP values of all sites'
                (1st dimension) order parameters (2nd dimension). 46 order
                parameters are computed per site: q_cn (coordination
                number), q_lin, 35 x q_bent (starting with a target angle
                of 5 degrees and, increasing by 5 degrees, until 175 degrees),
                q_tet, q_oct, q_bcc, q_2, q_4, q_6, q_reg_tri, q_sq, q_sq_pyr.
        """
        ops = OrderParameters(self._types, self._paras, 100.0)
        opvals = [[] for t in self._types]
        for i, site in enumerate(s.sites):
            neighcent = get_neighbors_of_site_with_index(
                    s, i, p=self.pneighs)
            #if self.pneighs is None:
            #    neighcent = get_neighbors_of_site_with_index(s, i)
            #else:
            #    neighcent = get_neighbors_of_site_with_index(
            #            s, i, approach=self.pneighs['approach'],
            #            delta=self.pneighs['delta'], cutoff=self.pneighs['cutoff'])
            neighcent.append(site)
            opvalstmp = ops.get_order_parameters(
                neighcent, len(neighcent)-1,
                indeces_neighs=[j for j in range(len(neighcent) - 1)])
            for j, opval in enumerate(opvalstmp):
                if opval is None:
                    opvals[j].append(0.0)
                else:
                    opvals[j].append(opval)
        return opvals

    def feature_labels(self):
        return self._labels

    def credits(self):
        return ("@article{zimmermann_jain_2017, title={Applications of order"
                " parameter feature vectors}, journal={in progress}, author={"
                "Zimmermann, N. E. R. and Jain, A.}, year={2017}}")

    def implementors(self):
        return ("Nils E. R. Zimmermann")


def get_order_parameter_stats(
        struct, pneighs=None, convert_none_to_zero=True, delta_op=0.01,
        ignore_op_types=None):
    """
    Determine the order parameter statistics accumulated across all sites
    in Structure object struct using the get_order_parameters function.

    Args:
        struct (Structure): input structure.
        pneighs (dict): specification and parameters of
                neighbor-finding approach (see
                get_neighbors_of_site_with_index function
                for more details).
        convert_none_to_zero (bool): flag indicating whether or not
                to convert None values in LSOPs to zero (cf.,
                get_order_parameters function).
        delta_op (float): bin size of histogram that is computed
                in order to identify peak locations.
        ignore_op_types ([str]): list of OP types to be ignored in
                output dictionary (e.g., ["cn", "bent"]). Default (None)
                will consider all OPs.

    Returns: ({}) dictionary, the keys of which represent
            the order parameter type (e.g., "bent5", "tet", "sq_pyr")
            and the values of which are dictionaries carring the
            statistics ("min", "max", "mean", "std", "peak1", "peak2").
    """
    opstats = {}
    optypes = ["cn", "lin"]
    for i in range(5, 180, 5):
        optypes.append("bent{}".format(i))
    for t in ["tet", "oct", "bcc", "q2", "q4", "q6", "reg_tri", "sq", "sq_pyr", "tri_bipyr"]:
        optypes.append(t)
    opvals = SitesOrderParameters(pneighs=pneighs).featurize(struct)
    for i, opstype in enumerate(opvals):
        if ignore_op_types is not None:
            if optypes[i] in ignore_op_types or \
                    ("bent" in ignore_op_types and i > 1 and i < 36):
                continue
        ops_hist = {}
        for op in opstype:
            b = round(op / delta_op) * delta_op
            if b in ops_hist.keys():
                ops_hist[b] += 1
            else:
                ops_hist[b] = 1
        ops = list(ops_hist.keys())
        hist = list(ops_hist.values())
        sorted_hist = sorted(hist, reverse=True)
        if len(sorted_hist) > 1:
            max1_hist, max2_hist = sorted_hist[0], sorted_hist[1]
        elif len(sorted_hist) > 0:
            max1_hist, max2_hist = sorted_hist[0], sorted_hist[0]
        else:
            raise RuntimeError("Could not compute OP histogram.")
        max1_idx = hist.index(max1_hist)
        max2_idx = hist.index(max2_hist)
        opstats[optypes[i]] = {
            "min": min(opstype),
            "max": max(opstype),
            "mean": np.mean(np.array(opstype)),
            "std": np.std(np.array(opstype)),
            "peak1": ops[max1_idx],
            "peak2": ops[max2_idx]}
    return opstats


def get_order_parameter_feature_vectors_difference(
        struct1, struct2, pneighs=None, convert_none_to_zero=True,
        delta_op=0.01, ignore_op_types=None):
    """
    Determine the difference vector between two order parameter-statistics
    feature vector resulting from two input structures.

    Args:
        struct1 (Structure): first input structure.
        struct2 (Structure): second input structure.
        pneighs (dict): specification and parameters of
                neighbor-finding approach (see
                get_neighbors_of_site_with_index function
                for more details).
        convert_none_to_zero (bool): flag indicating whether or not
                to convert None values in OPs to zero (cf.,
                get_order_parameters function).
        delta_op (float): bin size of histogram that is computed
                in order to identify peak locations (cf.,
                get_order_parameters_stats function).
        ignore_op_types ([str]): list of OP types to be ignored in
                output dictionary (cf., get_order_parameters_stats
                function).

    Returns: ([float]) difference vector between order
                parameter-statistics feature vectors obtained from the
                two input structures (structure 1 - structure 2).
    """
    d1 = get_order_parameter_stats(
            struct1, pneighs=pneighs,
            convert_none_to_zero=convert_none_to_zero,
            delta_op=delta_op,
            ignore_op_types=ignore_op_types)
    d2 = get_order_parameter_stats(
            struct2, pneighs=pneighs,
            convert_none_to_zero=convert_none_to_zero,
            delta_op=delta_op,
            ignore_op_types=ignore_op_types)
    v = []
    for optype, stats in d1.items():
        for stattype, val in stats.items():
            v.append(val - d2[optype][stattype])
    return np.array(v)


def get_neighbors_of_site_with_index_future(struct, n, approach="min_dist", \
        delta=0.1, cutoff=10.0):
    """
    Returns the neighbors of a given site using a specific neighbor-finding
    method.

    Args:
        struct (Structure): input structure.
        n (int): index of site in Structure object for which motif type
                is to be determined.
        approach (str): type of neighbor-finding approach, where
              "min_dist" will use the MinimumDistanceNN class,
              "voronoi" the VoronoiNN class, "min_OKeeffe" the
              MinimumOKeeffe class, and "min_VIRE" the MinimumVIRENN class.
        delta (float): tolerance involved in neighbor finding.
        cutoff (float): (large) radius to find tentative neighbors.

    Returns: neighbor sites.
    """

    warnings.warn('This function will go into Pymatgen very soon.')

    if approach == "min_dist":
        return MinimumDistanceNN(tol=delta, cutoff=cutoff).get_nn(
                struct, n)
    elif approach == "voronoi":
        return VoronoiNN(tol=delta, cutoff=cutoff).get_nn(
                struct, n)
    elif approach == "min_OKeeffe":
        return MinimumOKeeffeNN(tol=delta, cutoff=cutoff).get_nn(
                struct, n)
    elif approach == "min_VIRE":
        return MinimumVIRENN(tol=delta, cutoff=cutoff).get_nn(
                struct, n)
    else:
        raise RuntimeError("unsupported neighbor-finding method ({}).".format(
                approach))

def get_neighbors_of_site_with_index(struct, n, p=None):
    """
    Determine the neighbors around the site that has index n in the input
    Structure object struct, given the approach defined by parameters
    p.  All supported neighbor-finding approaches and listed and
    explained in the following.  All approaches start by creating a
    tentative list of neighbors using a large cutoff radius defined in
    parameter dictionary p via key "cutoff".
    "min_dist": find nearest neighbor and its distance d_nn; consider all
            neighbors which are within a distance of d_nn * (1 + delta),
            where delta is an additional parameter provided in the
            dictionary p via key "delta".
    "scaled_VIRE": compute the radii, r_i, of all sites on the basis of
            the valence-ionic radius evaluator (VIRE); consider all
            neighbors for which the distance to the central site is less
            than the sum of the radii multiplied by an a priori chosen
            parameter, delta,
            (i.e., dist < delta * (r_central + r_neighbor)).
    "min_relative_VIRE": same approach as "min_dist", except that we
            use relative distances (i.e., distances divided by the sum of the
            atom radii from VIRE).
    "min_relative_OKeeffe": same approach as "min_relative_VIRE", except
            that we use the bond valence parameters from O'Keeffe's bond valence
            method (J. Am. Chem. Soc. 1991, 3226-3229) to calculate
            relative distances.
    Args:
        struct (Structure): input structure.
        n (int): index of site in Structure object for which
                neighbors are to be determined.
        p (dict): specification (via "approach" key; default is "min_dist")
                and parameters of neighbor-finding approach.
                Default cutoff radius is 6 Angstrom (key: "cutoff").
                Other default parameters are as follows.
                min_dist: "delta": 0.15;
                min_relative_OKeeffe: "delta": 0.05;
                min_relative_VIRE: "delta": 0.05;
                scaled_VIRE: "delta": 2.
    Returns: ([site]) list of sites that are considered to be nearest
            neighbors to site with index n in Structure object struct.
    """
    warnings.warn('This function will be removed as soon as the equivalent function in Pymatgen works with the new near neighbor-finding classes.')

    sites = []
    if p is None:
        p = {"approach": "min_dist", "delta": 0.1,
             "cutoff": 6}

    if p["approach"] not in [
        "min_relative_OKeeffe", "min_dist", "min_relative_VIRE", \
            "scaled_VIRE"]:
        raise RuntimeError("Unsupported neighbor-finding approach"
                           " (\"{}\")".format(p["approach"]))

    if p["approach"] == "min_relative_OKeeffe" or p["approach"] == "min_dist":
        neighs_dists = struct.get_neighbors(struct[n], p["cutoff"])
        try:
            eln = struct[n].specie.element
        except:
            eln = struct[n].species_string
    elif p["approach"] == "scaled_VIRE" or p["approach"] == "min_relative_VIRE":
        vire = ValenceIonicRadiusEvaluator(struct)
        if np.linalg.norm(struct[n].coords - vire.structure[n].coords) > 1e-6:
            raise RuntimeError("Mismatch between input structure and VIRE structure.")
        neighs_dists = vire.structure.get_neighbors(vire.structure[n], p["cutoff"])
        rn = vire.radii[vire.structure[n].species_string]

    reldists_neighs = []
    for neigh, dist in neighs_dists:
        if p["approach"] == "scaled_VIRE":
            dscale = p["delta"] * (vire.radii[neigh.species_string] + rn)
            if dist < dscale:
                sites.append(neigh)
        elif p["approach"] == "min_relative_VIRE":
            reldists_neighs.append([dist / (
                vire.radii[neigh.species_string] + rn), neigh])
        elif p["approach"] == "min_relative_OKeeffe":
            try:
                el2 = neigh.specie.element
            except:
                el2 = neigh.species_string
            reldists_neighs.append([dist / get_okeeffe_distance_prediction(
                eln, el2), neigh])
        elif p["approach"] == "min_dist":
            reldists_neighs.append([dist, neigh])

    if p["approach"] == "min_relative_VIRE" or \
                    p["approach"] == "min_relative_OKeeffe" or \
                    p["approach"] == "min_dist":
        min_reldist = min([reldist for reldist, neigh in reldists_neighs])
        for reldist, neigh in reldists_neighs:
            if reldist / min_reldist < 1.0 + p["delta"]:
                sites.append(neigh)

    return sites
