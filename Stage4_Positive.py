from Music import Music
from ml_utils import *
import os
import numpy as np
from pyspark.mllib.linalg import SparseVector

np.set_printoptions(threshold=np.inf)
import time

os.environ['JAVA_HOME'] = "/Library/Java/JavaVirtualMachines/jdk1.8.0_211.jdk/Contents/Home"

memory = '6g'
pyspark_submit_args = ' --driver-memory ' + memory + ' pyspark-shell'
os.environ["PYSPARK_SUBMIT_ARGS"] = pyspark_submit_args

if __name__ == "__main__":
    start = time.time()
    music = Music()
    select_PID = music.Products.sortBy(lambda x: x[1], ascending=False).take(10)[9][0]
    print(select_PID)

    Positive_Reviews = music.og \
        .filter(lambda x: x.split("\t")[3] == select_PID) \
        .filter(lambda x: int(x.split("\t")[7]) >= 4) \
        .map(lambda x: (x.split("\t")[2], splitSentence(x.split("\t")[13]))) \
        .flatMap(Split) \
        .zipWithIndex() \
        .map(lambda x: (x[1], x[0]))

    Positive_Reviews_body = Positive_Reviews.map(lambda x: x[1][1])
    Positive_Reviews_collect = Positive_Reviews_body.collect()

    num_Postive_Sentence = Positive_Reviews.count()

    from pyspark.mllib.feature import HashingTF, IDF

    # Load documents (one per line).

    hashingTF = HashingTF()
    tf = hashingTF.transform(Positive_Reviews_body)

    idf = IDF().fit(tf)
    tfidf = idf.transform(tf)

    tfidf_T = tfidf \
        .zipWithIndex() \
        .flatMap(explode) \
        .map(lambda x: (x[1], [x[0], x[2]])) \
        .reduceByKey(lambda x, y: np.vstack([x, y])) \
        .map(lambda x: (x[0], np.array(x[1]).reshape(-1, 2))) \
        .map(lambda x: (x[0], x[1][x[1][:, 0].argsort()])) \
        .map(lambda x: (x[0], SparseVector(num_Postive_Sentence, x[1][:, 0], x[1][:, 1])))

    tfidf_matrix = IndexedRowMatrix(tfidf_T)

    cosine_similarity = tfidf_matrix.columnSimilarities()

    sim_matrix_full = cosine_similarity.entries \
        .flatMap(lambda x: ((x.j, x.i, x.value), (x.i, x.j, x.value)))

    avg_dist_each = sim_matrix_full \
        .map(lambda x: (x[0], x[1], 1 - x[2])) \
        .map(lambda x: (x[0], (1, x[2]))) \
        .reduceByKey(lambda x, y: (x[0] + y[0], x[1] + y[1])) \
        .map(lambda x: (x[0], x[1][1] + num_Postive_Sentence - x[1][0] - 1)) \
        .map(lambda x: (x[0], x[1] / (num_Postive_Sentence - 1)))

    avg_dist_overall = avg_dist_each.map(lambda x: (0, x[1])) \
                           .reduceByKey(lambda x, y: x + y) \
                           .values().collect()[0] / num_Postive_Sentence
    avg_dist_each_vector = np.array(avg_dist_each.collect())

    center_index = avg_dist_each_vector[avg_dist_each_vector[:, 1].argsort()][0, 0]

    center_sim = sim_matrix_full \
        .map(lambda x: (x[0], (x[1], x[2]))) \
        .filter(lambda x: x[0] == center_index) \
        .sortBy(lambda x: x[1][1], ascending=False) \
        .map(lambda x: x[1])

    f = open("Stage4_Positive.txt", "w")
    f.write("overall average_distance: " + str(avg_dist_overall) + "\n")
    f.write("the center index is: " + str(center_index) + "\n")
    f.write("the center sentence is: " + str(Positive_Reviews.lookup(center_index)) + "\n")
    f.write("the 10 closest sentences to center sentence is: " + "\n")
    for i in center_sim.take(10):
        index = i[0]
        f.write(str(Positive_Reviews.lookup(index)) + "\n")
    end = time.time()
    f.write("totoal time spent: " + str(end - start))
    f.close()
