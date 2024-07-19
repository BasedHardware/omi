/*
  Warnings:

  - A unique constraint covering the columns `[userId,index]` on the table `TrackingSession` will be added. If there are existing duplicate values, this will fail.
  - Added the required column `index` to the `TrackingSession` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "TrackingSession" ADD COLUMN     "index" INTEGER NOT NULL;

-- CreateIndex
CREATE UNIQUE INDEX "TrackingSession_userId_index_key" ON "TrackingSession"("userId", "index");
