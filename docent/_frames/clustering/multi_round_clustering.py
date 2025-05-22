import random

from docent._frames.clustering.cluster_assigner import ClusterAssigner, HybridClusterAssigner
from docent._frames.clustering.cluster_generator import propose_clusters
from docent._llm_util.types import LLMApiKeys
from docent._log_util import get_logger

logger = get_logger(__name__)


class Cluster:
    def __init__(self, centroid: str, indices: set[int]):
        self.centroid = centroid
        self.indices = indices

    def __len__(self) -> int:
        return len(self.indices)

    def overlap_ratio(self, other: "Cluster") -> float:
        if not self.indices:
            return 0.0
        return len(self.indices & other.indices) / len(self.indices)


class ClusterResult:
    def __init__(
        self, clusters: list[Cluster], centroid_indices: list[int], running_centroids: list[str]
    ):
        self.clusters = clusters
        self.centroid_indices = centroid_indices
        self.running_centroids = running_centroids


class ClusterProcessor:
    def __init__(self, assigner: ClusterAssigner, llm_api_keys: LLMApiKeys | None = None):
        self.assigner = assigner
        self.llm_api_keys = llm_api_keys
        self.SUBSET_THRESHOLD = 300

    async def run_attributes_through_clusters(
        self,
        attribs: list[str],
        cluster_centroids: list[str],
        centroid_indices: list[int] | None = None,
    ) -> list[Cluster]:
        logger.info(f"Running {len(attribs)} attributes through {len(cluster_centroids)} clusters")
        full_items: list[str] = []
        full_centroids: list[str] = []
        for _ in range(len(cluster_centroids)):
            full_items.extend(attribs)
        for centroid in cluster_centroids:
            full_centroids.extend([centroid] * len(attribs))

        results = await self.assigner.assign(
            full_items, full_centroids, llm_api_keys=self.llm_api_keys
        )

        if centroid_indices is None:
            centroid_indices = list(range(len(cluster_centroids)))

        clusters: list[Cluster] = []
        for i in centroid_indices:
            centroid = cluster_centroids[i]
            indices: set[int] = set()
            start_idx = i * len(results) // len(cluster_centroids)
            end_idx = (i + 1) * len(results) // len(cluster_centroids)
            for j, res in enumerate(results[start_idx:end_idx]):
                if res is not None and res[0]:
                    indices.add(j)
            clusters.append(Cluster(centroid=centroid, indices=indices))
        return clusters

    def remove_very_large_clusters(
        self, clusters: list[Cluster], centroids: list[str], exclusive_threshold: float = 0.5
    ) -> list[int]:
        bad_indices: list[int] = []
        if len(centroids) > 3:
            for i, cluster in enumerate(clusters):
                match_count = len(cluster.indices)
                match_threshold = exclusive_threshold * len(cluster.indices)
                if match_count >= match_threshold:
                    logger.info(
                        f"Found oversized cluster {i} with {match_count} >= {match_threshold} matches"
                    )
                    bad_indices.append(i)
        logger.info(f"Identified {len(bad_indices)} oversized clusters to remove")
        return bad_indices

    def find_high_overlap_pairs(
        self,
        clusters: list[Cluster],
        centroids: list[str],
        centroid_indices: list[int],
        exclusive_threshold: float,
    ) -> tuple[dict[int, int], list[tuple[float, int, int]]]:
        cluster_pair_counts: dict[int, int] = {}
        bad_pairs: list[tuple[float, int, int]] = []

        for i, c1_idx in enumerate(centroid_indices):
            for j, c2_idx in enumerate(centroid_indices):
                if i == j:
                    continue

                cluster1 = clusters[i]
                cluster2 = clusters[j]

                if not cluster1.indices:
                    continue

                ratio = cluster1.overlap_ratio(cluster2)
                if ratio < exclusive_threshold:
                    continue
                if len(cluster1) > len(cluster2):
                    continue

                cluster_pair_counts[c1_idx] = cluster_pair_counts.get(c1_idx, 0) + 1
                cluster_pair_counts[c2_idx] = cluster_pair_counts.get(c2_idx, 0) + 1
                bad_pairs.append((ratio, c1_idx, c2_idx))

        return cluster_pair_counts, bad_pairs

    def prune_clusters_of_high_overlap(
        self, clusters: list[Cluster], centroids: list[str], exclusive_threshold: float = 0.4
    ) -> ClusterResult:
        centroid_indices = list(range(len(centroids)))
        bad_indices = self.remove_very_large_clusters(clusters, centroids, exclusive_threshold=0.5)

        for index in bad_indices:
            centroid_indices.remove(index)
            logger.info(f"Removed {centroids[index]}")

        while True:
            cluster_pair_counts, bad_pairs = self.find_high_overlap_pairs(
                clusters, centroids, centroid_indices, exclusive_threshold
            )

            if not bad_pairs:
                break

            bad_pairs.sort(key=lambda x: x[0], reverse=True)
            removed = False

            # Remove large clusters that are in many high-overlap pairs
            for bad_pair in bad_pairs:
                if cluster_pair_counts[bad_pair[2]] > 1:
                    centroid_indices.remove(bad_pair[2])
                    removed = True
                    logger.info(f"Removed {centroids[bad_pair[2]]}")
                    break

            if removed:
                continue

            # Remove small clusters that are in high-overlap pairs
            for bad_pair in bad_pairs:
                centroid_indices.remove(bad_pair[1])
                logger.info(f"Removed {centroids[bad_pair[1]]}")
                break

        running_centroids = [centroids[i] for i in centroid_indices]
        return ClusterResult(clusters, centroid_indices, running_centroids)

    def display_cluster_overlap_info(self, clusters: list[Cluster]) -> None:
        counts: dict[int, int] = {}
        for cluster in clusters:
            for i in cluster.indices:
                counts[i] = counts.get(i, 0) + 1

        for cluster in clusters:
            total_indices = len(cluster.indices)
            if total_indices == 0:
                continue
            excluded_indices = sum(1 for i in cluster.indices if counts[i] == 1)
            logger.info(
                f"{cluster.centroid}: {excluded_indices / total_indices:.2f}, {total_indices}"
            )

    def get_residuals(
        self, clusters: list[Cluster], attribs: list[str]
    ) -> tuple[list[str], list[str]]:
        all_indices: set[int] = set()
        for cluster in clusters:
            all_indices.update(cluster.indices)

        new_residuals = [attribs[i] for i in range(len(attribs)) if i not in all_indices]
        finished = [attribs[i] for i in range(len(attribs)) if i in all_indices]
        return new_residuals, finished

    def prune_small_clusters(
        self,
        clusters: list[Cluster],
        centroids: list[str],
        exclusive_threshold: float = 0.5,
        remove_majorities: bool = True,
    ) -> ClusterResult:
        centroid_indices = list(range(len(centroids)))
        bad_indices = []

        if remove_majorities:
            bad_indices = self.remove_very_large_clusters(
                clusters, centroids, exclusive_threshold=0.5
            )

        for index in bad_indices:
            centroid_indices.remove(index)
            logger.info(f"Removed {centroids[index]}")

        while True:
            max_ratio = 0.0
            max_ratio_centroid = 0

            for i, c1_idx in enumerate(centroid_indices):
                for j, c2_idx in enumerate(centroid_indices):
                    if i == j:
                        continue

                    cluster1 = clusters[i]
                    cluster2 = clusters[j]

                    if not cluster1.indices:
                        continue

                    ratio = cluster1.overlap_ratio(cluster2)
                    if ratio < exclusive_threshold:
                        continue
                    if ratio > max_ratio:
                        max_ratio = ratio
                        max_ratio_centroid = c1_idx

            if max_ratio < exclusive_threshold:
                break

            centroid_indices.remove(max_ratio_centroid)
            logger.info(f"Removed {centroids[max_ratio_centroid]}")

        running_centroids = [centroids[i] for i in centroid_indices]
        return ClusterResult(clusters, centroid_indices, running_centroids)

    async def cluster_from_initial_proposal(
        self, attribs: list[str], attribute: str, cluster_centroids: list[str], num_rounds: int = 1
    ) -> list[str]:
        if not attribs:
            return []

        all_finished: list[str] = []
        large = len(attribs) > self.SUBSET_THRESHOLD

        if large:
            logger.info(
                f"Using subset of {self.SUBSET_THRESHOLD} attributes for initial clustering due to large input size"
            )
            attribs_subset = random.sample(attribs, self.SUBSET_THRESHOLD)
        else:
            attribs_subset = attribs

        initial_clusters = await self.run_attributes_through_clusters(
            attribs_subset, cluster_centroids
        )
        cluster_result = self.prune_clusters_of_high_overlap(
            initial_clusters, cluster_centroids, exclusive_threshold=0.4
        )

        running_centroids = cluster_result.running_centroids
        logger.info(
            f"After pruning: kept {len(running_centroids)} centroids, removed {len(cluster_centroids) - len(running_centroids)}"
        )

        if large:
            initial_clusters = await self.run_attributes_through_clusters(
                attribs, running_centroids, cluster_result.centroid_indices
            )
            cluster_result.clusters = initial_clusters

        self.display_cluster_overlap_info(cluster_result.clusters)
        new_residuals, finished = self.get_residuals(cluster_result.clusters, attribs)
        all_finished.extend(finished)

        logger.info(
            f"-------done with stage {num_rounds} of clustering, {len(new_residuals)} / {len(attribs)} residuals remaining-------"
        )

        final_round = False
        while True:
            num_rounds += 1
            proposed_centroids = await propose_clusters(
                new_residuals,
                n_clusters_list=[None],
                extra_instructions_list=[
                    f"Specifically focus on the following attribute: {attribute}. In addition, try your best to avoid the following existing clusters: {running_centroids}"
                ],
                feedback_list=None,
                k=1,
                llm_api_keys=self.llm_api_keys,
            )

            new_centroids = proposed_centroids[0]
            assert new_centroids is not None
            logger.info(f"Proposed {len(new_centroids)} new centroids for round {num_rounds}")

            large = len(new_residuals) > self.SUBSET_THRESHOLD
            if large:
                new_residuals_subset = random.sample(new_residuals, self.SUBSET_THRESHOLD)
            else:
                new_residuals_subset = new_residuals

            new_clusters = await self.run_attributes_through_clusters(
                new_residuals_subset, new_centroids
            )
            new_cluster_result = self.prune_small_clusters(
                new_clusters,
                new_centroids,
                exclusive_threshold=0.5,
                remove_majorities=(not final_round) or num_rounds > 3,
            )

            running_new_centroids = new_cluster_result.running_centroids

            # Skip queries for already finished items if using HybridClusterAssigner
            if isinstance(self.assigner, HybridClusterAssigner):
                for centroid in running_new_centroids:
                    self.assigner.primary.skip_queries(all_finished, centroid)

            if large:
                new_clusters = await self.run_attributes_through_clusters(
                    new_residuals, running_new_centroids, new_cluster_result.centroid_indices
                )
                new_cluster_result.clusters = new_clusters

            self.display_cluster_overlap_info(new_cluster_result.clusters)
            new_residuals, finished = self.get_residuals(new_cluster_result.clusters, new_residuals)
            all_finished.extend(finished)

            logger.info(
                f"-------done with stage {num_rounds} of clustering, {len(new_residuals)} / {len(attribs)} residuals remaining---------"
            )

            running_centroids.extend(running_new_centroids)

            if final_round or len(new_residuals) < 0.05 * len(attribs):
                logger.info(
                    f"Terminating clustering: final_round={final_round}, residuals_ratio={len(new_residuals)/len(attribs):.3f}"
                )
                break

            if len(new_residuals) < 0.1 * len(attribs) or num_rounds == 4:
                final_round = True

        logger.info(f"Clustering completed with {len(running_centroids)} total clusters")
        return running_centroids


async def cluster_from_initial_proposal(
    attribs: list[str],
    attribute: str,
    cluster_centroids: list[str],
    assigner: ClusterAssigner,
    llm_api_keys: LLMApiKeys | None = None,
    num_rounds: int = 1,
) -> list[str]:
    processor = ClusterProcessor(assigner, llm_api_keys)
    return await processor.cluster_from_initial_proposal(
        attribs, attribute, cluster_centroids, num_rounds
    )
